from pathlib import Path
import os,fcntl,signal,subprocess,select,time,json,errno,hashlib
O=Path(__file__).parent;P=O/'lease-fixture';P.write_bytes(b'bounded exclusive file lease fixture\n');fd=os.open(P,os.O_RDWR);children=[];caught=[];start=time.monotonic()
def alarm(s,f):raise TimeoutError('10s lease fixture bound')
def io(s,f):caught.append(s)
signal.signal(signal.SIGALRM,alarm);signal.signal(signal.SIGIO,io);signal.alarm(10)
def child(code):
 p=subprocess.Popen(['/usr/bin/python3','-B','-c',code,str(P)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True);children.append(p);return p
def gone(p):
 assert p.wait(timeout=2)==0
 try:os.killpg(p.pid,0)
 except ProcessLookupError:return
 raise AssertionError('owned fixture child group remains')
try:
 p=child("import sys;f=open(sys.argv[1],'rb');print('READY',flush=True);sys.stdin.buffer.read(1);f.close()")
 assert select.select([p.stdout],[],[],2)[0]and p.stdout.readline()==b'READY\n'
 try:fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_WRLCK)
 except OSError as e:assert e.errno==errno.EAGAIN
 else:raise AssertionError('write lease admitted competing reader')
 p.stdin.write(b'x');p.stdin.flush();gone(p)
 assert fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_WRLCK)==0
 assert fcntl.fcntl(fd,fcntl.F_GETLEASE)==fcntl.F_WRLCK
 assert os.pread(fd,128,0)==b'bounded exclusive file lease fixture\n'
 p=child("import sys;f=open(sys.argv[1],'rb');print(f.read().hex(),flush=True);f.close()")
 until=time.monotonic()+2
 while not caught and time.monotonic()<until:select.select([],[],[],0.01)
 assert caught and p.poll()is None and not select.select([p.stdout],[],[],0)[0]
 assert fcntl.fcntl(fd,fcntl.F_GETLEASE)!=fcntl.F_WRLCK
 fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_UNLCK);gone(p)
 assert bytes.fromhex(p.stdout.read().decode().strip())==b'bounded exclusive file lease fixture\n'
 caught.clear();fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_WRLCK)
 before=os.pread(fd,128,0);P.unlink()
 assert fcntl.fcntl(fd,fcntl.F_GETLEASE)==fcntl.F_WRLCK and not caught and os.pread(fd,128,0)==before
 fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_UNLCK)
 r=dict(state='PASS real ext4 exclusive lease: existing-reader拒绝/new-reader blocked+SIGIO/release+child0/own positional reads+unlink',existing_reader_rejected_EAGAIN=True,new_open_blocked_and_notified_SIGIO=True,breaking_lease_GETLEASE_detected=True,own_pread_and_unlink_verified=True,all_child_groups_gone=True,children=[p.pid for p in children],lease_break_seconds=Path('/proc/sys/fs/lease-break-time').read_text().strip(),seconds=time.monotonic()-start)
 (O/'lease-test-result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
finally:
 signal.alarm(0)
 try:fcntl.fcntl(fd,fcntl.F_SETLEASE,fcntl.F_UNLCK)
 finally:os.close(fd)
 for p in children:
  if p.poll()is None:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
 if P.exists():P.unlink()
