#!/usr/bin/env python3
"""Verify a ROOT certificate and emit a NEW immutable image-approval source."""
import argparse,json,hashlib,os,sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'linux-tests'))
import image_context as context

def emit(certificate,expected_sha,out):
    record=context.base.binding(certificate)
    context.require(record['sha256']==expected_sha,'external ROOT certificate SHA')
    cert=context.validate_certificate(context.read(record))
    context.require(not out.exists() and out.resolve()!=Path(context.approved_images.__file__).resolve(),'new source output only, never overwrite approvals')
    text='"""ROOT-reviewed one-image registration; checkpoint before execution."""\nREGISTRATIONS = '+repr({cert['artifacts']['bit']['sha256']:record})+'\n'
    with out.open('x') as stream:stream.write(text);stream.flush();os.fsync(stream.fileno())
    return context.base.binding(out)

def emit_physical(certificate,expected_sha,qualification,qualification_sha,out):
    row=context.base.binding(certificate)
    context.require(row['sha256']==expected_sha,'external ROOT image certificate SHA')
    cert=context.validate_certificate(context.read(row))
    registered,_=context.registration(cert['hardware'],cert['artifacts'])
    context.require(registered==row,'same already registered basic image certificate')
    q=context.base.binding(qualification)
    context.require(q['sha256']==qualification_sha,'external ROOT physical qualification SHA')
    context.validate_physical(cert,q)
    import approved_cost_images
    context.require(not out.exists() and out.resolve()!=Path(approved_cost_images.__file__).resolve(),'new COST source output only')
    text='"""ROOT-reviewed COST physical qualification; checkpoint before use."""\nPHYSICAL_REGISTRATIONS = '+repr({cert['artifacts']['bit']['sha256']:q})+'\n'
    with out.open('x') as stream:stream.write(text);stream.flush();os.fsync(stream.fileno())
    return context.base.binding(out)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--certificate',required=True,type=Path);p.add_argument('--certificate-sha256',required=True);p.add_argument('--out-new-approval-source',required=True,type=Path);p.add_argument('--kind',choices=('image','cost'),default='image');p.add_argument('--physical-qualification',type=Path);p.add_argument('--qualification-sha256');a=p.parse_args()
    if a.kind=='image':
        context.require(a.physical_qualification is None and a.qualification_sha256 is None,'image registration has no COST qualification argument')
        result=emit(a.certificate,a.certificate_sha256,a.out_new_approval_source)
    else:
        context.require(a.physical_qualification is not None and a.qualification_sha256 is not None,'actual COST qualification binding required')
        result=emit_physical(a.certificate,a.certificate_sha256,a.physical_qualification,a.qualification_sha256,a.out_new_approval_source)
    print(json.dumps(result))
if __name__=='__main__':main()
