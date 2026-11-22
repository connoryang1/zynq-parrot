"""Same split-volume sum rule as R9; explicit fresh profile supplied by caller."""
GiB=1024**3
MiB=1024**2

def violations(resources,elapsed,limits):
    """Reserve remaining allocations on their actual device, never across devices.

    A shared filesystem needs the sum of remaining allocations and the maximum
    floor on that filesystem. Free space observations use the conservative min.
    """
    reasons=[]
    for name in ('work_allocated_bytes','evidence_allocated_bytes'):
        if type(resources[name]) is not int or resources[name]<0:
            raise ValueError('invalid allocated byte count: '+name)
    work=resources['work_allocated_bytes'];evidence=resources['evidence_allocated_bytes']
    for name,used,cap in (('work',work,limits['work_cap_bytes']),('evidence',evidence,limits['evidence_cap_bytes'])):
        if used>cap:reasons.append(dict(kind='allocation_cap',name=name,actual=used,maximum=cap))
    requirements=(('work',limits['work_floor_bytes'],max(0,limits['work_cap_bytes']-work)+limits['other_work_future_bytes']),('home',limits['home_floor_bytes'],max(0,limits['evidence_cap_bytes']-evidence)+limits['other_home_future_bytes']),('shm',limits['shm_floor_bytes'],limits['other_shm_future_bytes']))
    devices={}
    for name,floor,remaining in requirements:
        volume=resources['volumes'][name]
        if type(volume['device']) is not int or type(volume['free_bytes']) is not int or volume['free_bytes']<0:
            raise ValueError('invalid volume record: '+name)
        group=devices.setdefault(volume['device'],dict(device=volume['device'],names=[],floor=0,remaining=0,free=volume['free_bytes']))
        group['names'].append(name);group['floor']=max(group['floor'],floor);group['remaining']+=remaining;group['free']=min(group['free'],volume['free_bytes'])
    for group in devices.values():
        minimum=group['floor']+group['remaining']
        if group['free']<minimum:
            reasons.append(dict(kind='volume_reserve',device=group['device'],names=group['names'],actual=group['free'],minimum=minimum,floor=group['floor'],remaining_allocation=group['remaining']))
    if elapsed is not None and elapsed>limits['deadline_seconds']:
        reasons.append(dict(kind='elapsed_bound',actual=elapsed,maximum=limits['deadline_seconds']))
    return reasons
