"""Source-extracted coverage/counter/reader functions; no historical toolROOT imports."""

import json,os,selectors,signal,struct,subprocess,threading,time

from pathlib import Path

from contract import require

BASE=0x80000000

class AuditInterrupted(RuntimeError):pass

def segments(path):
    raw=Path(path).read_bytes();require(raw[:6]==b'\x7fELF\x02\x01','ELF64LE')
    off=struct.unpack_from('<Q',raw,32)[0];size,count=struct.unpack_from('<HH',raw,54)
    result=[]
    for n in range(count):
        kind,flags,offset,va,pa,filesz,memsz,alignment=struct.unpack_from('<IIQQQQQQ',raw,off+n*size)
        if kind==1:
            require(va==pa and BASE<=pa and pa+memsz<=BASE+46*1024*1024,'physical ELF46MiB bounds')
            result.append(dict(address=pa,data=raw[offset:offset+filesz],memsz=memsz,flags=flags))
    require(result,'PT_LOAD segments');return result


def decode_nbf(path):
    image={};maximum=BASE;count=0
    for line in Path(path).read_text().splitlines():
        fields=line.split('_');require(len(fields)==3,'NBF record fields')
        op,address,value=(int(part,16) for part in fields)
        if op<=3 and address>=BASE:
            length=1<<op;require(address+length<=BASE+46*1024*1024,'actual NBF write tail bound')
            maximum=max(maximum,address+length);count+=1
            for n in range(length):image[address+n]=(value>>(8*n))&255
    return image,dict(write_records=count,maximum_write_end_exclusive=hex(maximum),allocation_bytes=46*1024*1024)


def verify_coverage(elf,nbf,config_address,config_value):
    # Independent converter readback: no use of its parsed mem dictionary.
    actual,bound=decode_nbf(nbf);missing=[];wrong=[];zero=0;total=0
    for segment in segments(elf):
        for n,byte in enumerate(segment['data']):
            address=segment['address']+n
            if config_address<=address<config_address+8:byte=(config_value>>(8*(address-config_address)))&255
            total+=1;zero+=byte==0
            if address not in actual:missing.append(address)
            elif actual[address]!=byte:wrong.append(address)
    require(not missing and not wrong,'file-backed NBF coverage missing=%d wrong=%d'%(len(missing),len(wrong)))
    return dict(file_bytes=total,file_zero_bytes=zero,missing_bytes=0,wrong_bytes=0,load_bound=bound,
                declared_input=dict(address=hex(config_address),bytes=8,value=hex(config_value)))


def primary_counts(lane,lines,values):
    expected=(lines,0,lines,0,8*lines,0) if lane=='i' else (0,lines,0,lines,0,8*lines)
    require(tuple(values)==expected,'primary retained-use counter gate: '+repr(values)+' expected '+repr(expected))


def kill_owned_reader(process):
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass


def guarded_reader(command,error_path,guard,timeout=3600):
    """Guard idle readers independently of data parsing; own exactly one PG."""
    guard();start=time.monotonic();process=None;watch=None;stop=threading.Event();errors=[];handlers={};failure=None;polls=[];late_error=None
    def interrupted(signum,frame):raise AuditInterrupted('audit caught signal '+str(signum))
    def monitor():
        last=time.monotonic()
        while not stop.wait(.25):
            try:
                now=time.monotonic();polls.append(now-last);require(now-last<=1,'audit guard poll gap over1s');last=now
                guard()
                require(now-start<timeout,'audit fixed reader deadline')
            except BaseException as error:
                errors.append(error);kill_owned_reader(process);return
    try:
        for sig in (signal.SIGTERM,signal.SIGINT):handlers[sig]=signal.signal(sig,interrupted)
        with error_path.open('wb') as error:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=error,start_new_session=True,bufsize=0)
            watch=threading.Thread(target=monitor,daemon=True);watch.start();pending=b''
            with selectors.DefaultSelector() as selected:
                selected.register(process.stdout,selectors.EVENT_READ)
                while selected.get_map():
                    if errors:raise errors[0]
                    require(time.monotonic()-start<timeout,'audit fixed reader deadline')
                    for key,event in selected.select(.1):
                        chunk=os.read(key.fileobj.fileno(),65536)
                        if not chunk:selected.unregister(key.fileobj);continue
                        pending+=chunk
                        while b'\n' in pending:
                            line,pending=pending.split(b'\n',1);require(len(line)<1024*1024,'bounded selected event line')
                            if errors:raise errors[0]
                            yield line.decode('utf-8')+'\n'
                        require(len(pending)<1024*1024,'bounded pending selected line')
                if errors:raise errors[0]
                if pending:yield pending.decode('utf-8')
                require(process.wait(timeout=max(.001,timeout-(time.monotonic()-start)))==0,'reader complete0')
                guard()
    except BaseException as error:
        failure=repr(error);raise
    finally:
        try:
            for sig in handlers:signal.signal(sig,signal.SIG_IGN)
            stop.set();end=time.monotonic()+5
            if process is not None:
                kill_owned_reader(process);process.wait(timeout=max(.001,end-time.monotonic()))
                if watch is not None:watch.join(timeout=max(.001,end-time.monotonic()));require(not watch.is_alive(),'audit guard thread did not stop')
                while True:
                    try:os.killpg(process.pid,0)
                    except ProcessLookupError:break
                    require(time.monotonic()<end,'reader group remains after5s cleanup');time.sleep(.01)
                if process.stdout is not None:process.stdout.close()
                if errors and failure is None:late_error=errors[0];failure=repr(late_error)
                receipt=dict(argv=command,owned_pgid=process.pid,returncode=process.returncode,failure=failure,
                             owned_group_remaining=False,guard_interval_s=.25,max_observed_poll_gap_s=max(polls,default=0),teardown_bound_s=5)
                error_path.with_suffix('.owned.json').write_text(json.dumps(receipt,indent=2)+'\n')
                if late_error is not None:raise late_error
        finally:
            for sig,handler in handlers.items():signal.signal(sig,handler)

