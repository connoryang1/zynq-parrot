"""Run real shell argument construction with inert host tool/SSH fixtures."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
LAUNCH=ROOT/'codex-skills/bp-fpga-synthesis/scripts/launch_synthesis.sh'
FARM=ROOT/'codex-skills/bp-synthesis-farm/scripts/farm_synthesis.sh'
TOP='4dadebbfdddfe958eff432b7f87280cfb9b5d991'
BP='7566c67aad9b93f5546fcc5e258e405402a47850'

MOCK='''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
tool=Path(sys.argv[0]).name;args=sys.argv[1:];base=Path(os.environ['FIXTURE'])
with (base/'calls.jsonl').open('a') as f:f.write(json.dumps(dict(tool=tool,args=args,direct_make_trace=os.environ.get('BP_CACHE_MISS_TRACE')))+'\\n')
if tool=='git':
 cwd=base/'repo';clean=[];i=0
 while i<len(args):
  if args[i] in ('-C','-c'):
   if args[i]=='-C':cwd=Path(args[i+1])
   i+=2
  else:clean.append(args[i]);i+=1
 if clean[:2]==['rev-parse','--show-toplevel']:print(base/'repo')
 elif clean[:2]==['rev-parse','--short']:print('4dadebbfd')
 elif clean[:2]==['rev-parse','HEAD']:print(os.environ['BP'] if str(cwd).endswith('black-parrot') else os.environ['TOP'])
 elif clean[:2]==['worktree','add']:
  out=Path(clean[-2]);out.mkdir(parents=True,exist_ok=True)
  for name in ['cosim/black-parrot-example/vivado','import/black-parrot','import/basejump_stl','import/black-parrot-subsystems']:(out/name).mkdir(parents=True,exist_ok=True)
  for name in ['import/basejump_stl/bsg_mem/bsg_mem_1rw_sync.sv','import/black-parrot/external/basejump_stl/bsg_mem/bsg_mem_1rw_sync.sv','import/black-parrot/external/HardFloat/source/HardFloat_primitives.v','import/black-parrot-subsystems/blackparrot/v/bp_axi_top.sv']:
   p=out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('HOST_TEST_ONLY')
elif tool=='tmux':
 if args[0]=='display-message':print(424242)
 elif args[0]=='has-session':sys.exit(1)
elif tool=='make':sys.exit(int(os.environ.get('FIXTURE_MAKE_RC','0')))
elif tool=='ssh':
 body=sys.stdin.read();(base/'remote.json').write_text(json.dumps(dict(args=args,body=body)))
 print('job=20261122T000000Z-4dadebbfd')
 print('FARM_JOB=20261122T000000Z-4dadebbfd')
 print('FARM_TOP='+os.environ['TOP']);print('FARM_BP='+os.environ['BP'])
 print('FARM_CFG=e_bp_unicore_zynqparrot_prefetch16k_cfg')
 print('FARM_LOG_ROOT=/HOST_TEST_ONLY/log');print('FARM_SOURCE=/HOST_TEST_ONLY/source')
'''


class Fixture:
    def __init__(self,path):
        self.base=path;self.repo=path/'repo';self.bin=path/'bin';self.bin.mkdir();self.repo.mkdir()
        self.scripts=self.repo/'codex-skills/bp-fpga-synthesis/scripts';self.scripts.mkdir(parents=True)
        self.launch=self.scripts/'launch_synthesis.sh';shutil.copyfile(LAUNCH,self.launch)
        self.farmdir=self.repo/'codex-skills/bp-synthesis-farm/scripts';self.farmdir.mkdir(parents=True)
        self.farm=self.farmdir/'farm_synthesis.sh';shutil.copyfile(FARM,self.farm)
        for name in ('check_build_ready.sh','accept_vivado_build.sh'):
            p=self.scripts/name;p.write_text('#!/bin/bash\nexit 0\n');p.chmod(0o755)
        for name in ('git','tmux','make','ssh'):
            p=self.bin/name;p.write_text(MOCK);p.chmod(0o755)
        for name in ('basejump_stl','HardFloat','bedrock'):
            p=self.repo/'import/black-parrot/external'/name/'.git';p.mkdir(parents=True)
        p=self.repo/'install/gen/v/rv_plic/rtl/rv_plic_reg_pkg.sv';p.parent.mkdir(parents=True);p.write_text('HOST_TEST_ONLY')
        self.env={k:v for k,v in os.environ.items() if not k.startswith(('FPGA_','ZP_','BP_'))}
        self.env.update(PATH=str(self.bin)+':'+self.env['PATH'],FIXTURE=str(path),TOP=TOP,BP=BP,ZP_REPO_DIR=str(self.repo),ZP_FPGA_LOG_ROOT=str(path/'logs'),ZP_FPGA_WORK_ROOT=str(path/'work'),FPGA_CFG='e_bp_unicore_zynqparrot_prefetch16k_cfg',FPGA_VIVADO_THREADS='8',FPGA_ACLK_MHZ='20',BP_FARM_MANIFEST_ROOT=str(path/'farm-manifests'))
    def run(self,script,args,setting=None,extra=None):
        env=dict(self.env)
        if setting is not None:env['FPGA_CACHE_MISS_TRACE']=setting
        env.update(extra or {})
        return subprocess.run(['bash',str(script),*args],env=env,text=True,capture_output=True,timeout=15)
    def calls(self):return [json.loads(s) for s in (self.base/'calls.jsonl').read_text().splitlines()]


class Carrier(unittest.TestCase):
    def test_actual_tmux_worker_array_explicit_setting_and_unset(self):
        for setting in (None,'0','1'):
            with self.subTest(setting=setting),tempfile.TemporaryDirectory() as td:
                f=Fixture(Path(td));r=f.run(f.launch,['start'],setting);self.assertEqual(r.returncode,0,r.stderr)
                call=next(c for c in f.calls() if c['tool']=='tmux' and c['args'][0]=='new-session')
                words=shlex.split(call['args'][-1]);self.assertIn('FPGA_CACHE_MISS_TRACE='+(setting or ''),words)
                self.assertIn('FPGA_VIVADO_THREADS=8',words);self.assertIn('FPGA_ACLK_MHZ=20',words)

    def test_actual_worker_make_argv_revision_and_stale_environment(self):
        for setting in (None,'0','1'):
            with self.subTest(setting=setting),tempfile.TemporaryDirectory() as td:
                f=Fixture(Path(td));job='20261122T000000Z-4dadebbfd';(f.base/'logs'/job).mkdir(parents=True)
                r=f.run(f.launch,['worker',job,TOP],setting,dict(BP_CACHE_MISS_TRACE='opposite_stale_value'))
                self.assertEqual(r.returncode,0,r.stderr);makes=[c for c in f.calls() if c['tool']=='make'];self.assertEqual(len(makes),2)
                for call in makes:
                    self.assertIsNone(call['direct_make_trace'])
                    expected=[] if setting is None else ['BP_CACHE_MISS_TRACE='+setting]
                    self.assertEqual([s for s in call['args'] if s.startswith('BP_CACHE_MISS_TRACE=')],expected)
                    self.assertIn('THREADS=8',call['args']);self.assertIn('ACLK_MHZ=20',call['args'])
                self.assertIn('cache_miss_trace='+(setting or 'default'),(f.base/'logs'/job/'revisions.txt').read_text())
                self.assertEqual((f.base/'logs'/job/'status').read_text().strip(),'PASS')

    def test_invalid_setting_refused_before_tools_and_make_failure_preserved(self):
        for value in ('2','-1','01','true','0 1'):
            with tempfile.TemporaryDirectory() as td:
                f=Fixture(Path(td));r=f.run(f.launch,['start'],value);self.assertEqual(r.returncode,2)
                self.assertFalse((f.base/'calls.jsonl').exists())
        with tempfile.TemporaryDirectory() as td:
            f=Fixture(Path(td));job='20261122T000000Z-4dadebbfd';(f.base/'logs'/job).mkdir(parents=True)
            r=f.run(f.launch,['worker',job,TOP],'0',dict(FIXTURE_MAKE_RC='7'))
            self.assertEqual(r.returncode,7);self.assertEqual((f.base/'logs'/job/'status').read_text().strip(),'FAIL')

    def test_actual_farm_ssh_argument_and_remote_named_forwarding(self):
        for setting in (None,'0','1'):
            with self.subTest(setting=setting),tempfile.TemporaryDirectory() as td:
                f=Fixture(Path(td));extra={k:'HOST_TEST_ONLY' for k in ('BP_SYNTH_DECISION','BP_SYNTH_CHEAPER_GATES','BP_SYNTH_PASS_ACTION','BP_SYNTH_FAIL_ACTION')}
                r=f.run(f.farm,['admit','bp1','fixture','topbranch','bpbranch','1','e_bp_unicore_zynqparrot_prefetch16k_cfg'],extra=extra);self.assertEqual(r.returncode,0,r.stderr)
                r=f.run(f.farm,['launch','bp1','fixture','topbranch','bpbranch','8'],setting);self.assertEqual(r.returncode,0,r.stderr)
                remote=json.loads((f.base/'remote.json').read_text());self.assertEqual(remote['args'][-1],setting or '')
                self.assertIn('cache_miss_trace=$6',remote['body']);self.assertIn('FPGA_CACHE_MISS_TRACE="$cache_miss_trace"',remote['body'])


if __name__=='__main__':unittest.main()
