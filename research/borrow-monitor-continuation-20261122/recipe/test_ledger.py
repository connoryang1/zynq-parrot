"""Pure process-record fixtures only; no process/vendor/launcher spawned."""
import copy,unittest
from ownership_ledger import Ledger

def proc(pid,start,parent):return dict(pid=pid,startticks=start,ppid=parent,pgrp=100,sid=100,argv_tokens=['test-record'])
def snap(rows,worker=None):
 worker=worker or proc(100,1,10)
 return dict(worker=worker,status='RUNNING',descendants=rows,worker_group=rows,all_vivado=[],global_vendor_tools=[])
class Tests(unittest.TestCase):
 def test_proved_orphan_and_new_child(self):
  w=proc(100,1,10);child=proc(101,2,100);l=Ledger(w);l.snapshot(snap([w,child]),'oldpoll');child['ppid']=1;new=proc(102,3,101);s=snap([w,child,new]);s['global_vendor_tools']=[child,new];p=l.snapshot(s,'newpoll');self.assertFalse(p['foreign_vendor_tools']);self.assertEqual(p['proven_orphans'],[[101,2]]);self.assertEqual(l.events[-1]['parent'],[101,2])
 def test_same_group_token_is_not_ownership(self):
  w=proc(100,1,10);l=Ledger(w);l.snapshot(snap([w]),'old');unknown=proc(102,3,1);s=snap([w,unknown]);s['global_vendor_tools']=[unknown];p=l.snapshot(s,'new');self.assertEqual(len(p['foreign_vendor_tools']),1);self.assertEqual(len(l.events),1)
 def test_pid_reuse_and_session_change_rejected(self):
  w=proc(100,1,10);l=Ledger(w);child=proc(101,2,100);l.snapshot(snap([w,child]),'old')
  for field,value in [('startticks',3),('sid',200),('pgrp',200)]:
   bad=copy.deepcopy(child);bad[field]=value
   with self.assertRaises(ValueError):l.snapshot(snap([w,bad]),'bad')
 def test_dead_parent_cannot_prove_new_orphan(self):
  w=proc(100,1,10);l=Ledger(w);l.snapshot(snap([w,proc(101,2,100)]),'old');unknown=proc(102,3,101);s=snap([w,unknown]);s['global_vendor_tools']=[unknown];self.assertTrue(l.snapshot(s,'new')['foreign_vendor_tools'])
 def test_terminal_absence_and_worker_reuse(self):
  w=proc(100,1,10);l=Ledger(w);l.snapshot(snap([w]),'old');s=snap([]);s['worker']=None;s['status']='PASS';self.assertEqual(l.snapshot(s,'end')['owned_current'],[])
  bad=proc(100,9,10)
  with self.assertRaises(ValueError):l.snapshot(snap([bad],worker=bad),'reuse')
if __name__=='__main__':unittest.main()
