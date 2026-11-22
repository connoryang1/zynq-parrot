"""UNEXECUTED small parser-negative/equivalence fixtures; no reader/model."""
import copy
import json
from pathlib import Path
import unittest
import profile_replay as replay

HERE=Path(__file__).resolve().parent


class HeaderCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=json.loads((HERE/'plan.DRAFT.json').read_text())
        cls.original,cls.candidate,_,_=replay.load_sources(cls.plan)

    def fixture(self):
        names=('be.clk','i.bclk','i.cclk','d.bclk','d.cclk')
        selected={key:(key,1) for key in names}
        selected['payload']=('payload',512)
        header=['#FST\t0\t100\t-12\n']+[
            '#SIGNAL\t%s\t%d\t%d\t%s\n'%(key,width,n+1,suffix)
            for n,(key,(suffix,width)) in enumerate(selected.items())]
        data=['0\t%d\t%s\n'%(n+1,'0'*width)
            for n,(_,width) in enumerate(selected.values())]
        data+=['1\t1\t1\n','1\t6\t'+'x'*512+'\n',
               '2\t1\t0\n','2\t6\t'+'z'*512+'\n','3\t1\t1\n']
        return selected,header,data

    def outcome(self,edges,lines,selected):
        try:return ('accepted',list(edges(iter(lines),selected)))
        except ValueError as error:return ('rejected',str(error))

    def test_only_three_literal_parser_edits(self):
        original=(HERE/'parser-original.py').read_text()
        expected=original.replace(
            '    mapping={};widths={};values={};changes={};time=None;ended=False\n',
            '    mapping={};widths={};values={};changes={};time=None;ended=False;schema_complete=False\n')
        expected=expected.replace("            require(not ended and len(parts)==3 and set(mapping)==set(selected),'complete event schema')\n",
            "            require(not ended and len(parts)==3 and (schema_complete or set(mapping)==set(selected)),'complete event schema')\n")
        line="            time=current;require(handle not in changes,'one settled value per timestamp');changes[handle]=None if set(bits)&set('xz') else int(bits,2)\n"
        expected=expected.replace(line,line+'            schema_complete=True\n')
        self.assertEqual(expected,(HERE/'parser-candidate.py').read_text())
        self.assertEqual(original[original.index('class Validator:'):],expected[expected.index('class Validator:'):])

    def test_valid_complete_clock_payload_unknowns_and_extra_FST_are_equal(self):
        selected,header,data=self.fixture()
        for lines in (header+data+['#END\n'],header+data+['#FST\t0\t100\t-12\n','#END\n']):
            old=self.outcome(self.original.edges,lines,selected)
            self.assertEqual(old[0],'accepted')
            self.assertEqual(old,self.outcome(self.candidate.edges,lines,selected))

    def test_malformed_before_and_after_cached_header_are_rejected_identically(self):
        selected,header,data=self.fixture()
        valid=header+data+['#END\n']
        cases={
            'missing_declaration':header[:-1]+data+['#END\n'],
            'duplicate_declaration_before_data':header+[header[1]]+data+['#END\n'],
            'wrong_declaration_width':[s.replace('be.clk\t1\t','be.clk\t2\t') for s in header]+data+['#END\n'],
            'declaration_after_first_valid_data':header+[data[0],header[1]]+data[1:]+['#END\n'],
            'declaration_after_several_valid_data':header+data+[header[-1],'#END\n'],
            'first_record_wrong_fields':header+['0\t1\t0\textra\n']+data+['#END\n'],
            'cached_record_wrong_fields':header+data+['4\t1\t0\textra\n','#END\n'],
            'cached_unknown_handle':header+data+['4\t999\t0\n','#END\n'],
            'cached_wrong_width':header+data+['4\t1\t01\n','#END\n'],
            'cached_bad_bit':header+data+['4\t1\t2\n','#END\n'],
            'cached_full_payload_wrong_width':header+data+['4\t6\t'+'0'*511+'\n','#END\n'],
            'cached_full_payload_bad_bit':header+data+['4\t6\t'+'0'*511+'2\n','#END\n'],
            'decreasing_timestamp':header+data+['0\t1\t0\n','#END\n'],
            'duplicate_settled_value':header+data+['3\t1\t0\n','#END\n'],
            'duplicate_EOF':valid+['#END\n'],
            'event_after_EOF':valid+['4\t1\t0\n'],
            'missing_EOF':header+data,
        }
        for name,lines in cases.items():
            with self.subTest(case=name):
                old=self.outcome(self.original.edges,lines,selected)
                self.assertEqual(old[0],'rejected')
                self.assertEqual(old,self.outcome(self.candidate.edges,lines,selected))


if __name__=='__main__':unittest.main()
