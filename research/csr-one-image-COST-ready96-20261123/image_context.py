"""One-image CSR registration and ordinary deployed-allocation API trust."""
import json
import re
from pathlib import Path
import retained29_protocol as base
import retained29_stage_v2 as stage
import approved_images

require=base.require
BP='1e7aa2fdc94a56373a26f95b145aff361d4d0aaa'
TOPS={256:'a44c03bb7bc520a3b5727c2bb619a055a7ed5acd',768:'1b24c915ed628f6d47a382b3aa89fb662884e1a1'}
LIBCMA='126301f9575d119f3b12e41bc2ce26df79a0fdae210169da3bf4b6548dd1fdd3'
HERE=Path(__file__).resolve().parent
BASIC_SOURCE_NAMES=('image_context.py','approved_images.py','functional_protocol.py','functional.py')
COST_SOURCE_NAMES=(*BASIC_SOURCE_NAMES,'approved_cost_images.py','cost_protocol.py','cost_session.py','cohort_protocol.py','collect.py','analyze.py')

def source_names(cost=False):
    names=COST_SOURCE_NAMES if cost else BASIC_SOURCE_NAMES
    return tuple(str((HERE/n).relative_to(base.ROOT)) for n in names)

def read(row):
    base.verify_binding(row)
    return json.loads(Path(row['path']).read_text())

def validate_certificate(cert):
    require(cert['schema']=='csr-one-image-ROOT-certificate-v1' and cert['state']=='PASS ROOT-reviewed physical CSR image and deployed API contract'
        and cert['ROOT_verified'] is True,'actual ROOT certificate required')
    n=cert['lines_per_side']
    require(type(n) is int and n in TOPS and cert['TOP']==TOPS[n] and cert['BP']==BP,'exact BP1e7 CSR256 or768 source')
    h=cert['hardware']
    require(h['retained']==dict(i_lines=n,d_lines=n,set_log2=8) and h['l1i_bytes']==h['l1d_bytes']==32768
        and h['l2_bytes']==16384 and h['cfg']=='e_bp_unicore_zynqparrot_prefetch16k_cfg','ordinary geometry/profile unchanged')
    artifacts=cert['artifacts']
    require(set(artifacts)=={'bit','hwh','map','package','fit','nbf','kernel_verification'},'full exact-image artifacts')
    for row in artifacts.values():base.verify_binding(row)
    require(artifacts['nbf']['sha256']==base.NBF_SHA and artifacts['kernel_verification']['sha256']==base.KERNEL_PROOF_SHA,'kernel29/46MiB proof')
    fit=read(artifacts['fit'])
    require(str(fit['state']).startswith('routed-fit-and-package-PASS') and fit['bit_sha256']==artifacts['bit']['sha256']
        and fit['package_sha256']==artifacts['package']['sha256'],'actual closed fit/package')
    bundle=stage.local_bundle(dict(artifacts=artifacts))
    require(all(bundle['members'][k]=={v:artifacts[k][v] for v in ('bytes','sha256')} for k in ('bit','hwh','map')),'package BIT/HWH/MAP equality')
    for key in ('canonical_fullcore','source_bridge','clock_topology','build_profile','API_provenance','normal_shutdown_scope'):
        base.verify_binding(cert[key])
    profile=read(cert['build_profile'])
    expected=dict(BP_RETAINED_BUFFER=1,BP_RETAINED_I_LINES=n,BP_RETAINED_D_LINES=n,BP_RETAINED_SETS=256,
        BP_RETAINED_OBSERVE=1,BP_AXI_RESPONSE_DELAY=0,BP_CACHE_MISS_TRACE=0)
    require(profile['TOP']==cert['TOP'] and profile['BP']==BP and profile['bit_sha256']==artifacts['bit']['sha256']
        and profile['epoch_bits']==8 and profile['line_bytes']==64,'same built source/full payload profile')
    contexts=profile['contexts']
    require(len(contexts)==3 and {r['project'] for r in contexts}=={'top_ip_proj','black_parrot_bd_proj','tmp_edit_project'},'three actual define contexts')
    for row in contexts:
        require(row['defines']==expected and all(type(v) is int for v in row['defines'].values()),'all seven actual defines')
        base.verify_binding(row['receipt'])
    for key in ('config','revision_record','XPR','child_commands'):base.verify_binding(profile[key])
    clocks=read(cert['clock_topology'])
    require(clocks['scope']=='actual-FPGA-clock-topology' and clocks['bit_sha256']==artifacts['bit']['sha256']
        and clocks['core_hz']==clocks['axi_hz']==20000000 and clocks['timer_hz']==8000000,'physical20/8MHz, not simulation')
    source=read(cert['source_bridge'])
    require(source['schema']=='csr-one-image-source-qualification-v1' and source['ROOT_verified'] is True
        and source['TOP']==cert['TOP'] and source['BP']==BP and source['bit_sha256']==artifacts['bit']['sha256']
        and source['canonical_fullcore']==cert['canonical_fullcore'] and source['i_lines']==source['d_lines']==n
        and source['sets']==256 and source['epoch_bits']==8 and source['cache_miss_trace']==0,
        'actual normalized source/native qualification, no old source approval')
    for key in ('compiled_sources','parameters','strict_payload','counter'):
        base.verify_binding(source[key])
    allocation=cert['allocation_contract']
    require(allocation==dict(method='successful-deployed-allocation-api-contract-v1',runner_sha256=base.RUNNER_SHA,
        helper_sha256=base.HELPER_SHA,libcma_sha256=LIBCMA,allocation_bytes=48234496,cacheable=0,
        extent_basis='Successful deployed cma_alloc(requested_bytes,0) owns the requested extent; no returned-size getter claimed',
        kernel_source_binary_equivalence_required=False,live_kernel_table_required=False),'accepted deployed API trust, no invented getter')
    scope=read(cert['normal_shutdown_scope'])
    require(scope['ROOT_verified'] is True and scope['method']=='normal-Linux-SBI-shutdown-plus-verified-safe-recovery'
        and scope['stop_printf_is_halt'] is False and scope['abnormal_timeout_is_accepted_result'] is False,
        'explicit normal-shutdown assumption and failure scope')
    require(cert['application_runtime']==dict(runner_sha256=base.RUNNER_SHA,helper_sha256=base.HELPER_SHA,application_gp0=False),'exact2dd primary; no9c substitution')
    return cert

def registration(hardware,artifacts):
    require(Path(approved_images.__file__).resolve()==HERE/'approved_images.py','exact sibling approval source')
    bit=artifacts['bit']['sha256']
    require(bit in approved_images.REGISTRATIONS,'image approvals empty or bit unregistered')
    record=approved_images.REGISTRATIONS[bit]
    cert=validate_certificate(read(record))
    require(cert['hardware']==hardware,'registered exact hardware')
    for key in ('nbf','package','bit','fit','kernel_verification'):
        require(cert['artifacts'][key]==artifacts[key],'registered artifact identity '+key)
    return record,cert

def validate_physical(cert,record):
    n=cert['lines_per_side'];h=cert['hardware'];artifacts=cert['artifacts']
    qualification=read(record)
    require(qualification['schema']=='bp-retained29-physical-capacity-qualification-v1'
        and qualification['state']=='PASS root-reviewed actual physical capacity/source/clock qualification'
        and qualification['platform']=='FPGA' and qualification['hardware']==h
        and qualification['artifacts']=={k:artifacts[k] for k in ('nbf','package','bit','fit','kernel_verification')},
        'actual same-image physical prerequisite')
    runtime=qualification['observer_runtime']
    require(runtime['runner_sha256']!=base.RUNNER_SHA and runtime['profile']!='old2dd-no-application-gp0-v1'
        and all(k in runtime for k in ('source_proof','execution_proof')),
        'separate actually qualified capacity observer, not primary substitution')
    for key in ('source_proof','execution_proof'):base.verify_binding(runtime[key])
    require([r['role'] for r in qualification['cases']]==['d-enabled','d-off','i-enabled'],'all physical capacity roles')
    for row in qualification['cases']:
        words=[0]*6 if row['role']=='d-off' else ([0,n,0,n,0,8*n] if row['role']=='d-enabled' else [n,0,n,0,8*n,0])
        require(row['lines']==n and row['counter_words']==words and row['complete'] is True
            and row['all_payloads_checked'] is True and row['observer_stable'] is True and row['saturated'] is False
            and row['recovery_verified'] is True and row['primary_use_rejected']==(row['role']=='d-off'),
            'physical full capacity/negative/stable/nonsaturated checks unchanged')
        for key in ('receipt','fixture','checker'):base.verify_binding(row[key])
    require(qualification['canonical_fullcore']==cert['canonical_fullcore']
        and qualification['source_bridge']==cert['source_bridge'] and qualification['clock_topology']==cert['clock_topology'],
        'same actual per-image canonical/source/clock qualification')
    return qualification

def physical(record,hardware,artifacts):
    _,cert=registration(hardware,artifacts)
    # This module is imported only on the COST path; present/fixed do not depend
    # on a later COST approval source or require an observer before capability.
    import approved_cost_images
    require(Path(approved_cost_images.__file__).resolve()==HERE/'approved_cost_images.py','exact sibling COST approval source')
    require(approved_cost_images.PHYSICAL_REGISTRATIONS.get(artifacts['bit']['sha256'])==record,
        'actual COST physical qualification not registered')
    qualification=validate_physical(cert,record)
    runtime=qualification['observer_runtime']
    return dict(cert,approved_observer_runtime={k:runtime[k] for k in ('runner_sha256','source_proof','execution_proof')})

def actual_allocation(text,hardware,artifacts):
    registration_record,cert=registration(hardware,artifacts)
    # Existing parser separately checks complete Linux46MiB and terminal output.
    values=re.findall(r'allocate_dram\(\) called with size 48234496 bytes --> virtual ptr=(0x[0-9a-fA-F]+), physical ptr=0x([0-9a-fA-F]+)',text)
    require(len(values)==1,'one actual successful old2dd allocation pointer record')
    virtual,physical=(int(v,16) for v in values[0])
    require(0<virtual<0xffffffff and 0<physical and physical+48234496<=2**32,'NULL/MAP_FAILED/physical addition overflow')
    return dict(method=cert['allocation_contract']['method'],registration=registration_record,virtual=virtual,physical_base=physical,
        owned_bytes=48234496,physical_end_exclusive=physical+48234496,extent_source='successful deployed allocation API contract',
        kernel_table_read=False,returned_size_getter=False,application_gp0=False)
