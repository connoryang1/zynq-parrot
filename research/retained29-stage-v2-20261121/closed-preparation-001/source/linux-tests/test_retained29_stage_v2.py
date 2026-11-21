"""Host-only cache/reuse/space tests; no SSH, upload, overlay, or board call."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import retained29_protocol as p
import retained29_stage_v2 as stage


def fixture():
    admission=dict(host='xilinx@192.168.4.35',artifacts=dict(nbf=dict(path='/local/new.nbf',bytes=70907577,sha256='a'*64),
        package=dict(path='/local/package.b64',bytes=1775321,sha256='b'*64),bit=dict(sha256='c'*64)))
    bundle=dict(stem='black_parrot_bd_1',members={s:dict(bytes=n,sha256=h*64) for s,n,h in
        (('bit',4045685,'c'),('hwh',311517,'d'),('map',81,'e'))})
    paths=stage.request_paths(admission,bundle,'blackparrot_bd_1');expected=stage.expected_files(admission,bundle)
    inventory=dict(files={name:dict(path=path,device=1,missing=False,bytes=expected[name]['bytes'],sha256=expected[name]['sha256']) for name,path in paths.items()},
        filesystems={'1':dict(device=1,allocation_unit=4096,available_bytes=512*1024*1024,available_inodes=100)})
    return admission,bundle,inventory


class CachePlan(unittest.TestCase):
    def test_prior_full_stage_exact_sync_and_nbf_binding(self):
        a,_,_=fixture()
        markers=['PACKAGE_OK=1','PACKAGE_SHA256='+a['artifacts']['package']['sha256'],'STAGE_DURABLE_SYNC_OK=1',
                 'NBF_OK=new.nbf:'+a['artifacts']['nbf']['sha256'],'BOARD_BIT_SHA256='+a['artifacts']['bit']['sha256'],'STAGE_OK=1']
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'stage.log';path.write_text('\n'.join(markers)+'\n')
            stage.verify_prior_durable_stage(a,p.binding(path))
            for line in markers:
                path.write_text('\n'.join(x for x in markers if x!=line)+'\n')
                with self.subTest(line=line),self.assertRaises(ValueError):stage.verify_prior_durable_stage(a,p.binding(path))
            path.write_text('\n'.join(markers[::-1])+'\n')
            with self.assertRaises(ValueError):stage.verify_prior_durable_stage(a,p.binding(path))

    def test_all_exact_zero_stage_allocation_even_zero_free(self):
        a,b,i=fixture();i['filesystems']['1'].update(available_bytes=0,available_inodes=0)
        decision=stage.plan(a,b,'blackparrot_bd_1',i)
        self.assertEqual(decision['action'],'reuse-complete');self.assertFalse(decision['stage_required'])
        self.assertEqual((decision['stage_allocated_bytes'],decision['stage_allocated_inodes']),(0,0))
        with self.assertRaises(ValueError):stage.helper_argv(a,decision,Path('/snapshot'))

    def test_every_file_hash_and_size_is_required(self):
        for key in fixture()[2]['files']:
            for field,value in (('sha256','0'*64),('bytes',0),('missing',True)):
                a,b,i=fixture()
                if field=='missing':i['files'][key]={k:v for k,v in i['files'][key].items() if k in ('path','device','missing')}
                i['files'][key][field]=value
                with self.subTest(key=key,field=field),self.assertRaisesRegex(ValueError,'rollback'):
                    stage.plan(a,b,'blackparrot_bd_1',i)

    def test_no_unreadable_partial_or_wrong_path_as_cache_hit(self):
        for change in ('extra','missing-key','wrong-path','unknown-device','nonboolean-missing','bad-statvfs'):
            a,b,i=fixture()
            if change=='extra':i['files']['unexpected']={}
            elif change=='missing-key':del i['files']['load.map']
            elif change=='wrong-path':i['files']['nbf']['path']+='.incoming'
            elif change=='unknown-device':i['files']['nbf']['device']=7
            elif change=='nonboolean-missing':i['files']['nbf']['missing']=0
            else:i['filesystems']['1']['allocation_unit']=0
            with self.subTest(change=change),self.assertRaises(ValueError):stage.plan(a,b,'blackparrot_bd_1',i)

    def rollback_fixture(self):
        a,b,i=fixture();temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        rollback={}
        for suffix in stage.SUFFIXES:
            path=Path(temp.name)/('original.'+suffix);path.write_bytes(('old '+suffix).encode())
            rollback[suffix]=p.binding(path)
            i['files']['load.'+suffix].update(bytes=rollback[suffix]['bytes'],sha256=rollback[suffix]['sha256'])
        return a,b,i,rollback

    def test_exact_nbf_reuse_omits_duplicate_incoming(self):
        a,b,i,rollback=self.rollback_fixture()
        decision=stage.plan(a,b,'blackparrot_bd_1',i,rollback)
        self.assertEqual(decision['action'],'stage-package-only');self.assertFalse(decision['stage_nbf'])
        argv=stage.helper_argv(a,decision,Path('/snapshot'))
        self.assertEqual(len(argv),3);self.assertNotIn(a['artifacts']['nbf']['path'],argv)
        budget=decision['budget']['1'];self.assertLess(budget['target_bytes'],12*1024*1024)
        self.assertEqual(budget['required_bytes'],budget['target_bytes']+budget['rollback_bytes']+stage.MUTATION_RESERVE_BYTES)
        i['files']['nbf']['sha256']='0'*64
        full=stage.plan(a,b,'blackparrot_bd_1',i,rollback)
        self.assertEqual(full['action'],'stage-package-and-nbf')
        self.assertEqual(stage.helper_argv(a,full,Path('/snapshot'))[-1],a['artifacts']['nbf']['path'])
        self.assertEqual(full['budget']['1']['target_bytes']-budget['target_bytes'],((70907577+4095)//4096)*4096)

    def test_partial_nbf_reuse_fits_50MB_full_duplicate_refused(self):
        a,b,i,rollback=self.rollback_fixture();i['filesystems']['1']['available_bytes']=50*1024*1024
        stage.plan(a,b,'blackparrot_bd_1',i,rollback)
        i['files']['nbf']['missing']=True
        i['files']['nbf']={k:v for k,v in i['files']['nbf'].items() if k in ('path','device','missing')}
        with self.assertRaisesRegex(ValueError,'insufficient.*bytes'):stage.plan(a,b,'blackparrot_bd_1',i,rollback)

    def test_rollback_identity_bytes_and_inodes_fail_before_stage(self):
        for fault in ('remote-original','local-original','no-bytes','no-inodes'):
            a,b,i,rollback=self.rollback_fixture()
            if fault=='remote-original':i['files']['load.hwh']['sha256']='0'*64
            elif fault=='local-original':Path(rollback['map']['path']).write_bytes(b'changed')
            elif fault=='no-bytes':i['filesystems']['1']['available_bytes']=0
            else:i['filesystems']['1']['available_inodes']=0
            with self.subTest(fault=fault),self.assertRaises(ValueError):stage.plan(a,b,'blackparrot_bd_1',i,rollback)

    def test_per_filesystem_budget_no_cross_mount_credit(self):
        a,b,i,rollback=self.rollback_fixture()
        i['files']['package']['device']=2
        i['filesystems']['2']=dict(device=2,allocation_unit=4096,available_bytes=0,available_inodes=100)
        with self.assertRaisesRegex(ValueError,'filesystem 2'):stage.plan(a,b,'blackparrot_bd_1',i,rollback)

    def test_remote_audit_local_execution_is_read_only_and_refuses_symlink(self):
        # Run the exact remote Python body on local temporary files only.
        import subprocess,sys
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'data';path.write_bytes(b'known bytes')
            request={'file':str(path),'missing':str(Path(tmp)/'absent')}
            proc=subprocess.run([sys.executable,'-c',stage.REMOTE_AUDIT,json.dumps(request)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0);inv=json.loads(proc.stdout)
            self.assertEqual(inv['files']['file']['sha256'],hashlib.sha256(b'known bytes').hexdigest())
            self.assertTrue(inv['files']['missing']['missing']);self.assertEqual(path.read_bytes(),b'known bytes')
            link=Path(tmp)/'link';link.symlink_to(path)
            proc=subprocess.run([sys.executable,'-c',stage.REMOTE_AUDIT,json.dumps({'link':str(link)})],capture_output=True,text=True)
            self.assertNotEqual(proc.returncode,0)


if __name__=='__main__':unittest.main()
