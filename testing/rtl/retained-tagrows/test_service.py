"""Host fixtures for the independent accepted-edge service checker, no model."""
import unittest
from service import Audit,NAMES


class ServiceTests(unittest.TestCase):
    def edge(self,a,**values):
        old={k:'0'*w for k,w in NAMES.items()}
        defaults=dict(lookup_ready_o=3,resp_ready_i=3)
        defaults.update(values)
        for k,v in defaults.items():old[k]=format(v,'0%db'%NAMES[k])
        new=dict(old,clk_i='01')
        a.step(old,new)

    def miss(self,a,delay):
        self.edge(a,lookup_v_i=1,lookup_addr0_i=0x1000000)
        for _ in range(delay-1):self.edge(a)
        self.edge(a,resp_v_o=1)

    def test_row_and_fallback_boundaries(self):
        for lines,sets,rows in [([1280,1280],256,True),([259,517],256,True),([0,0],256,True),
                               ([0,1280],256,True),([1280,0],256,True),([2048,2048],256,True),
                               ([2049,2049],256,False),([1280,1280],64,False)]:
            self.assertEqual(Audit(lines,sets).rows,rows)

    def test_three_cycle_row_miss_and_wrong_age_rejected(self):
        a=Audit([1280,1280],256);self.miss(a,3)
        self.assertEqual(a.samples['lane0/empty_miss'],[3])
        for delay in (2,4,11):
            with self.assertRaisesRegex(ValueError,'measured service'):self.miss(Audit([1280,1280],256),delay)

    def test_partial_set_service_uses_actual_slot_count(self):
        a=Audit([2049,2049],256)
        self.assertEqual(a.expected_service(0,0,0x1000000,'empty_miss'),19)
        self.assertEqual(a.expected_service(0,1,0x1000040,'fill_insert'),26)
        self.assertEqual(a.expected_service(0,1,0x1000000,'fill_insert'),28)

    def test_payload_and_terminal_ownership_are_independent(self):
        a=Audit([1280,1280],256)
        with self.assertRaisesRegex(ValueError,'unmatched'):self.edge(a,resp_v_o=1)
        self.edge(a,lookup_v_i=1,lookup_addr0_i=0x1000000)
        with self.assertRaisesRegex(ValueError,'overlapping'):self.edge(a,lookup_v_i=1,lookup_addr0_i=0x1000000)
        with self.assertRaisesRegex(ValueError,'owned operation'):a.finish([[1,0,0,0,0],[0,0,0,0,0]])
        b=Audit([1280,1280],256);b.counts[0][0]=1
        self.edge(b,lookup_v_i=1,lookup_addr0_i=0x1000011)
        for _ in range(11):self.edge(b)
        with self.assertRaisesRegex(ValueError,'payload mismatch'):self.edge(b,resp_v_o=1,resp_hit_o=1)

    def test_row_clear_cost_separate_and_exact(self):
        a=Audit([1280,1280],256);self.edge(a,clear_i=1,lookup_ready_o=0)
        for _ in range(256):self.edge(a,lookup_ready_o=0)
        self.edge(a)
        self.assertEqual(a.clear_samples[0],[257])
        b=Audit([1280,1280],256);self.edge(b,clear_i=1,lookup_ready_o=0)
        for _ in range(255):self.edge(b,lookup_ready_o=0)
        with self.assertRaisesRegex(ValueError,'clear sweep'):self.edge(b)

    def test_service_includes_endpoint_and_preserves_serial_formula(self):
        row=Audit([1280,1280],256);serial=Audit([1280,1280],64)
        for way in range(5):
            self.assertEqual(row.expected_service(0,0,0x1000000+way*256*64,'all_slot_hit'),12)
            self.assertEqual(serial.expected_service(0,0,0x1000000+way*64*64,'all_slot_hit'),12+2*way)
        self.miss(serial,41)
        self.assertEqual(serial.samples['lane0/empty_miss'],[41])


if __name__=='__main__':unittest.main()
