import io
import unittest
from service import Audit, NAMES, analyze_vcd, payload, prefix


def initial():
    return {name:'0' for name in NAMES}


def rise(a,state,lane=0,**changes):
    old=dict(state);old.update({k:'0' for k in ('lookup_v_i','insert_v_i','resp_v_o','insert_done_o','insert_published_o')});old['clk_i']='0';old.update({k:bin(v)[2:] for k,v in changes.items()})
    new=dict(old);new['clk_i']=bin(1<<lane)[2:]
    a.step(old,new);state.update(new)


class Tests(unittest.TestCase):
    def test_zero_complete_and_edge_cost(self):
        a=Audit([0,0],256);s=initial()
        for lane in range(2):
            base=0x1000000+lane*0x400000
            rise(a,s,lane,lookup_v_i=1<<lane,lookup_ready_o=1<<lane,**{f'lookup_addr{lane}_i':base})
            rise(a,s,lane)
            rise(a,s,lane,resp_v_o=1<<lane,resp_ready_i=1<<lane)
            rise(a,s,lane,insert_v_i=1<<lane,insert_ready_o=1<<lane,**{f'insert_addr{lane}_i':base,f'insert_data{lane}_i':payload(base)})
            rise(a,s,lane,insert_done_o=1<<lane)
        r=a.finish([[1,1,1,1,0],[1,1,1,1,0]])
        self.assertEqual(r['lane0/empty_miss']['median'],2)
        self.assertEqual(r['lane1/disabled_insert']['median'],1)
    def test_own_clock_only(self):
        a=Audit([0,0],256);s=initial()
        rise(a,s,1);rise(a,s,1);rise(a,s,0)
        self.assertEqual(a.edge,[1,2])
    def test_unowned_response(self):
        a=Audit([0,0],256)
        with self.assertRaisesRegex(ValueError,'unmatched'):rise(a,initial(),resp_v_o=1,resp_ready_i=1)
    def test_duplicate_lookup(self):
        a=Audit([0,0],256);s=initial()
        kw=dict(lookup_v_i=1,lookup_ready_o=1,lookup_addr0_i=0x1000000)
        rise(a,s,**kw)
        with self.assertRaisesRegex(ValueError,'overlapping'):rise(a,s,**kw)
    def test_eof_pending(self):
        a=Audit([0,0],256);rise(a,initial(),lookup_v_i=1,lookup_ready_o=1,lookup_addr0_i=0x1000000)
        with self.assertRaisesRegex(ValueError,'EOF'):a.finish([[0]*5]*2)
    def test_payload_fail_closed(self):
        a=Audit([1,0],256)
        with self.assertRaisesRegex(ValueError,'insert payload'):rise(a,initial(),insert_v_i=1,insert_ready_o=1,insert_addr0_i=0x1000000,insert_data0_i=7)
    def test_unknown_qualified(self):
        a=Audit([0,0],256);old=initial();old.update(resp_v_o='1',resp_ready_i='1',clk_i='x')
        with self.assertRaisesRegex(ValueError,'unknown'):a.step(old,dict(old,clk_i='1'))
    def test_prefix_partial_geometry(self):
        q,i=prefix(0,1320,256)
        self.assertEqual(len(q),1325)
        self.assertEqual(i[1320][0],0x1000000+1536*64)
        self.assertEqual(len({x[0] for x in i[:1320]}),1320)
    def test_incomplete_vcd_reject(self):
        with self.assertRaisesRegex(ValueError,'incomplete'):analyze_vcd(io.StringIO('$scope module top $end\n'),Audit([0,0],256))
    def test_duplicate_alias_reject(self):
        v='$var wire 2 a clk_i $end\n$var wire 2 b clk_i $end\n'
        with self.assertRaisesRegex(ValueError,'ambiguous'):analyze_vcd(io.StringIO(v),Audit([0,0],256))

if __name__=='__main__':unittest.main()
