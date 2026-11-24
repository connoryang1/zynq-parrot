#!/usr/bin/env python3
"""One serialized PYNQ-Z2 Linux session for the fg/bg retained-line benchmark.

Sequence (every step checked; any failure -> recovery):
  power cycle -> wait ready -> stage package -> load overlay -> verify bit SHA
  -> FCLK0 31.25->50 MHz (core 20 MHz, RTC 8 MHz per the routed MMCM)
  -> RAM-backed kernel29 NBF with the timer64 firmware fix (symlinked)
  -> install EOF-fixed controller 6caf (original saved, restored at the end)
  -> boot Linux, transfer guest ELF over the console, verify SHA, run cases
  -> poweroff -> restore controller/NBF link -> power cycle -> default overlay.
Console transcript and a JSON record go to --out. No result is interpreted here.
"""
import argparse, base64, gzip, hashlib, json, os, re, shlex, subprocess, sys, time
from pathlib import Path
import pexpect

HOST = 'xilinx@192.168.4.35'
SCRIPTS = Path('/home/coyang/zynq-parrot-linux-capacity/codex-skills/bp-fpga-synthesis/scripts')
ZDIR = '/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq'
BOARD_NBF = 'linux-retained-control29-accepted-rootfs-mem46-shell.nbf'
NBF_SHA = '1a06cae9ce4c93eeb634d109ce1e58d6b7d6cade85ec966e7bcd848828ef9d33'
SESSION_NBF = 'fgbg-kernel29-timer64.nbf'
TIMERS = {0x80006bf8: (0x8082014143889381, 0x8082014163889381),
          0x80006c38: (0x01416422c398577d, 0x01416422e398577d)}
CTRL_ORIG = '2dd9c411614af250'
CTRL_NEW = Path('/home/coyang/fpga-artifacts/context-resume/host-stdin-eof-fix-20261123/compile02/remote/candidate/control-program')
PROMPT = re.compile(r'(?:^|\r?\n)(?:~ )?# ')
GUEST = '/tmp/fgbg'
LOCAL_NBF_DIR = Path('/run/user/1001/zp-fgbg-nbf')
LOCAL_ORIG_NBF = Path('/home/coyang/fpga-artifacts/context-resume/retained-control-kernel29-20261121/package/linux-retained-control29-accepted-rootfs-mem46-shell.nbf')

def sh(cmd, out, label, timeout=600, env=None, check=True):
    t = time.monotonic()
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       timeout=timeout, env=env)
    (out / f'{label}.log').write_text(r.stdout)
    if check and r.returncode:
        raise RuntimeError(f'{label} rc={r.returncode}: {r.stdout[-500:]}')
    return r.stdout, time.monotonic() - t

def ssh(command, out, label, timeout=300, check=True):
    return sh(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', HOST, command],
              out, label, timeout, check=check)[0]

def power_env():
    text = Path('/home/coyang/power_cycle.sh').read_text()
    m = re.search(r'(https?://\S+?)["\'\s]', text)
    if not m: raise RuntimeError('power endpoint not found')
    return dict(os.environ, PYNQ_POWER_STATE_URL=m.group(1))

def power_cycle(out, tag):
    sh([str(SCRIPTS / 'power_cycle_pynq.sh'), HOST], out, f'{tag}-power', 300, env=power_env())
    sh([str(SCRIPTS / 'wait_pynq_ready.sh'), HOST], out, f'{tag}-ready', 400)

CLOCK_RPC = r'''
import json,sys
from pynq.ps import Clocks
k=('fclk0_mhz','fclk1_mhz','fclk2_mhz','fclk3_mhz')
b={x:getattr(Clocks,x) for x in k}
if sys.argv[1]=='set50': Clocks.fclk0_mhz=50.0
a={x:getattr(Clocks,x) for x in k}
print('CLOCKS '+json.dumps(dict(before=b,after=a)))
'''

def clocks(out, label, action):
    text = ssh('sudo -n python3 -B -c ' + shlex.quote(CLOCK_RPC) + ' ' + action, out, label, 120)
    m = re.search(r'CLOCKS (\{.*\})', text)
    if not m: raise RuntimeError('clock RPC failed: ' + text[-300:])
    return json.loads(m.group(1))

PATCH_RPC = r'''
import hashlib,os,sys
src,dst=sys.argv[1],sys.argv[2]
T={%s}
h=hashlib.sha256();n=0
with open(src,'rb') as f, open(dst+'.tmp','wb') as g:
    for line in f:
        h.update(line)
        p=line.rstrip(b'\n').split(b'_')
        if len(p)==3 and int(p[1],16) in T:
            a=int(p[1],16);o,new=T[a]
            assert int(p[2],16)==o,(hex(a),p[2])
            line=b'03_%%016x_%%016x\n'%%(a,new);n+=1
        g.write(line)
assert h.hexdigest()==%r and n==2,(h.hexdigest(),n)
os.rename(dst+'.tmp',dst)
print('PATCHED',n)
''' % (','.join(f'{a}:({o},{n})' for a, (o, n) in TIMERS.items()), NBF_SHA)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--package', required=True, type=Path)
    ap.add_argument('--elf', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--case', action='append', required=True,
                    help='benchmark argument string, e.g. "64 4 8 12 64 scan scan d"')
    ap.add_argument('--runtime-ms', type=int, default=3_600_000)
    a = ap.parse_args()
    out = a.out; out.mkdir(parents=True, exist_ok=False)
    rec = dict(started=time.time(), cases=a.case, host=HOST, steps=[])
    def save(): (out / 'session.json').write_text(json.dumps(rec, indent=2) + '\n')
    elf = a.elf.read_bytes(); elf_sha = hashlib.sha256(elf).hexdigest()
    rec['elf_sha256'] = elf_sha
    idle = ssh('pgrep -x control-program || echo IDLE; ls -d ~/bp-logs/.control-program.lock 2>/dev/null || true', out, 'idle')
    if 'IDLE' not in idle or '.control-program.lock' in idle:
        raise RuntimeError('board busy')
    ctrl_installed = False
    try:
        power_cycle(out, 'initial')
        stage, _ = sh([str(SCRIPTS / 'stage_pynq_artifacts.sh'), str(a.package), HOST], out, 'stage', 900)
        bit_sha = re.search(r'BIT_SHA256=([0-9a-f]{64})', stage).group(1); rec['bit_sha256'] = bit_sha
        sh([str(SCRIPTS / 'load_pynq_overlay.sh'), HOST], out, 'overlay', 300)
        rec['clock_initial'] = clocks(out, 'clock-initial', 'read')
        rec['clock_set'] = clocks(out, 'clock-set', 'set50')
        c = rec['clock_set']['after']
        if c['fclk0_mhz'] != 50.0: raise RuntimeError('FCLK0 not 50 MHz: %r' % c)
        # RAM-backed timer64 NBF; the persistent original is never modified.
        ssh(f'cd {ZDIR} && rm -f /dev/shm/{SESSION_NBF} && python3 -B -c {shlex.quote(PATCH_RPC)} '
            f'{BOARD_NBF} /dev/shm/{SESSION_NBF} && ln -sfn /dev/shm/{SESSION_NBF} {SESSION_NBF}', out, 'nbf', 300)
        nbf_sha = ssh(f'sha256sum /dev/shm/{SESSION_NBF}', out, 'nbf-sha').split()[0]; rec['nbf_sha256'] = nbf_sha
        # Controller: keep the original as control-program.orig-2dd and install 6caf.
        sh(['scp', '-q', str(CTRL_NEW), f'{HOST}:/dev/shm/control-program.6caf'], out, 'ctrl-upload')
        ssh(f'cd {ZDIR} && sha256sum control-program | grep -q ^{CTRL_ORIG} && cp -p control-program control-program.orig-2dd '
            f'&& cp /dev/shm/control-program.6caf control-program.new && chmod 755 control-program.new && mv control-program.new control-program', out, 'ctrl-install')
        ctrl_installed = True
        ctrl_sha = ssh(f'sha256sum {ZDIR}/control-program', out, 'ctrl-sha').split()[0]; rec['ctrl_sha256'] = ctrl_sha
        rec['clock_pre_guest'] = clocks(out, 'clock-pre-guest', 'read')
        save()
        env = dict(os.environ, PYNQ_CONTROL_PROGRAM_SHA256=ctrl_sha, PYNQ_BITSTREAM_SHA256=bit_sha,
                   PYNQ_CONTROL_PROGRAM_TIMEOUT_MS=str(a.runtime_ms))
        local_nbf = LOCAL_NBF_DIR / SESSION_NBF
        if not local_nbf.exists():
            LOCAL_NBF_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.run([sys.executable, '-B', '-c', PATCH_RPC, str(LOCAL_ORIG_NBF), str(local_nbf)], check=True)
        if hashlib.sha256(local_nbf.read_bytes()).hexdigest() != nbf_sha:
            raise RuntimeError('local/remote patched NBF differ')
        child = pexpect.spawn(str(SCRIPTS / 'run_pynq_interactive.sh'), [HOST, str(local_nbf)],
                              env=env, encoding='utf-8', timeout=600, codec_errors='replace')
        child.setwinsize(50, 200)
        with (out / 'console.log').open('w') as log:
            child.logfile_read = log
            child.expect(PROMPT, timeout=900); rec['steps'].append(('boot', time.time()))
            payload = base64.b64encode(gzip.compress(elf, 9)).decode()
            child.sendline(f': > {GUEST}.b64'); child.expect(PROMPT, timeout=60)
            for i in range(0, len(payload), 76):
                child.sendline(f"echo '{payload[i:i+76]}' >> {GUEST}.b64"); child.expect(PROMPT, timeout=120)
            child.sendline(f'base64 -d {GUEST}.b64 | gunzip > {GUEST} && chmod +x {GUEST} && sha256sum {GUEST}')
            child.expect(r'([0-9a-f]{64})  ' + GUEST, timeout=120)
            if child.match.group(1) != elf_sha: raise RuntimeError('guest ELF hash mismatch')
            child.expect(PROMPT, timeout=60); rec['steps'].append(('transfer', time.time())); save()
            for i, case in enumerate(a.case):
                child.sendline(f'echo FGBG_CASE_BEGIN {i}; {GUEST} {case}; echo FGBG_CASE_EXIT {i} rc=$?')
                child.expect(rf'FGBG_CASE_EXIT {i} rc=(\d+)', timeout=a.runtime_ms // 1000)
                rc = int(child.match.group(1)); rec['steps'].append(('case', i, rc, time.time())); save()
                child.expect(PROMPT, timeout=60)
                if rc: raise RuntimeError(f'case {i} rc={rc}')
            child.sendline('poweroff -f')
            child.expect(r'CORE(?:\[0\])? PASS', timeout=300)
            child.expect(pexpect.EOF, timeout=300)
        child.close(); rec['runner_exit'] = child.exitstatus
        rec['state'] = 'PASS' if child.exitstatus == 0 else 'RUNNER_FAIL'
    except Exception as e:
        rec['state'] = 'FAIL'; rec['error'] = repr(e)
    finally:
        save()
        try:
            if ctrl_installed:
                ssh(f'cd {ZDIR} && cp -p control-program.orig-2dd control-program && sha256sum control-program | grep -q ^{CTRL_ORIG}', out, 'ctrl-restore', check=False)
            ssh(f'cd {ZDIR} && rm -f {SESSION_NBF} /dev/shm/{SESSION_NBF} /dev/shm/control-program.6caf', out, 'nbf-restore', check=False)
            power_cycle(out, 'final')
            rec['clock_final'] = clocks(out, 'clock-final', 'read')
            rec['recovered'] = True
        except Exception as e:
            rec['recovered'] = False; rec['recovery_error'] = repr(e)
        rec['finished'] = time.time(); save()
    print(rec['state'], out)

if __name__ == '__main__':
    main()
