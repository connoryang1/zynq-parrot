"""Exact opt-in91653 immutable-selection edges function; no old ROOT imports."""
from csr1536_support import require


def edges(lines,selected):
    mapping={};widths={};values={};changes={};time=None;ended=False;schema_complete=False
    clocks=('be.clk','i.bclk','i.cclk','d.bclk','d.cclk')
    def sample(t,updates):
        rising=[key for key in clocks if values.get(mapping[key])==0 and updates.get(mapping[key],values.get(mapping[key]))==1]
        if rising:yield t,rising,{key:values.get(handle) for key,handle in mapping.items()}
        values.update(updates)
    for line in lines:
        parts=line.rstrip('\n').split('\t')
        if parts[0]=='#SIGNAL':
            require(time is None and len(parts)==5,'signal declaration order');_,key,width,handle,name=parts
            require(key in selected and key not in mapping and int(width)==selected[key][1],'exact selected signal/width')
            suffix=selected[key][0];require(name==suffix or name.endswith('.'+suffix),'exact selected path')
            mapping[key]=int(handle);widths[int(handle)]=int(width)
        elif parts[0]=='#FST':require(len(parts)==4 and int(parts[2])>int(parts[1]),'nonempty FST')
        elif parts[0]=='#END':require(not ended,'duplicate EOF');ended=True
        else:
            require(not ended and len(parts)==3 and (schema_complete or set(mapping)==set(selected)),'complete event schema')
            current,handle=int(parts[0]),int(parts[1]);bits=parts[2].lower()
            require(handle in widths and len(bits)==widths[handle] and set(bits)<=set('01xz'),'known event format')
            require(time is None or current>=time,'monotonic time')
            if time is not None and current!=time:yield from sample(time,changes);changes={}
            time=current;require(handle not in changes,'one settled value per timestamp');changes[handle]=None if set(bits)&set('xz') else int(bits,2)
            schema_complete=True
    require(ended and time is not None,'closed complete FST');yield from sample(time,changes)
