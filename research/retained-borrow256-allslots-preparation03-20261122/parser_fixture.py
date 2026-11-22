"""CPU-bound immutable full167 parser fixture, no FST reader/model."""
import time,threading

def exercise(c,guard,seconds=6,mutable=None):
    chosen=c.original.audit.selection();start=time.monotonic();events=[0];stamps=[0]
    def lines():
        yield '#FST\t0\t999999999999\t-12\n'
        for i,(key,(suffix,width)) in enumerate(chosen.items(),1):yield '#SIGNAL\t%s\t%d\t%d\tTOP.%s\n'%(key,width,i,suffix)
        t=0
        while time.monotonic()-start<seconds:
            for i,(key,(_,width)) in enumerate(chosen.items(),1):
                value=t&1 if key in ('be.clk','i.bclk','i.cclk','d.bclk','d.cclk') else (i+t)&((1<<width)-1)
                events[0]+=1;yield '%d\t%d\t%s\n'%(t,i,format(value,'0%db'%width))
            t+=1;stamps[0]=t
        yield '#END\n'
    edges=0
    stop=threading.Event();errors=[];background_calls=[0]
    def reader_monitor_callbacks():
        while not stop.wait(.25):
            try:guard();background_calls[0]+=1
            except BaseException as e:errors.append(repr(e));return
    thread=threading.Thread(target=reader_monitor_callbacks,daemon=True);thread.start()
    saved=open(mutable,'wb') if mutable is not None else None
    try:
        for _ in c.original.audit.edges(lines(),chosen):
            edges+=1;guard()
            if errors:raise ValueError('concurrent reader-monitor callback failed '+str(errors))
            if saved is not None and edges%64==0:saved.write(b'fixture-output\n');saved.flush()
    finally:
        if saved is not None:saved.close()
        stop.set();thread.join(timeout=1)
        if thread.is_alive():raise ValueError('fixture reader-monitor callback thread did not stop')
        if errors:raise ValueError('fixture concurrent callback failure '+str(errors))
    guard()
    return dict(background_callbacks=background_calls[0],background_callback_thread_joined=True,mutable_bytes=__import__('pathlib').Path(mutable).stat().st_size if mutable is not None else 0,scope='CPU-bound exact167 selected-event parser fixture only; no semantic hardware proof',seconds=time.monotonic()-start,event_lines=events[0],timestamps=stamps[0],rising_samples=edges)
