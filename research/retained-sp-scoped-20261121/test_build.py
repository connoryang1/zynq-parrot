import copy
import gzip
import io
import tempfile
import unittest
from pathlib import Path
from build_clone import guarded_commands, filtered_source, changed_files
from canonical import canonicalize, declarations, equivalent
from common import PREFIX, SYMS, proposal


class BuilderGuards(unittest.TestCase):
    def test_actual_commands_and_text_header(self):
        p=proposal();compile,link=guarded_commands(p)
        self.assertEqual(compile[-5],PREFIX+'__pch.h')
        self.assertEqual(link[1:3],['ps.o','main.o'])
        self.assertEqual(compile[:-6],p['compile_argv'][:-6])

    def test_changed_pch_flags_rejected(self):
        p=copy.deepcopy(proposal());p['original_PCH_creation_argv'].insert(1,'-DOTHER=1')
        with self.assertRaisesRegex(ValueError,'PCH compiler'):guarded_commands(p)

    def test_legacy_host_object_order_rejected(self):
        p=copy.deepcopy(proposal());p['link_argv'][1:3]=['main.o','ps.o']
        with self.assertRaisesRegex(ValueError,'object order'):guarded_commands(p)

    def test_missing_trace_flag_rejected(self):
        p=copy.deepcopy(proposal());p['compile_argv'].remove('-DVM_TRACE=1')
        # Keep PCH prefixes consistent: the independent TRACE guard must reject.
        p['original_PCH_creation_argv'].remove('-DVM_TRACE=1')
        p['textual_header_compile_argv'].remove('-DVM_TRACE=1')
        with self.assertRaisesRegex(ValueError,'TRACE'):guarded_commands(p)

    def test_filter_is_only_after_registration_before_open(self):
        text='before\n        __Vm_modelp->trace(__Vm_dumperp, 0, 0);\n        __Vm_dumperp->open(name);\nafter\n'
        new,addition=filtered_source(text,[dict(path='TOP.a[0].tag',width=20)])
        self.assertEqual(new.replace(addition,''),text)
        self.assertIn('dumpvars(1, "TOP.a[0].tag")',new)
        self.assertLess(new.index('dumpvars'),new.index('open('))
        with self.assertRaises(ValueError):filtered_source(text+text,[])

    def test_changed_eval_and_unexpected_files_rejected(self):
        before={n:dict(bytes=1,sha256='a') for n in
                (SYMS+'.cpp',SYMS+'.o','eval.o')}
        after=copy.deepcopy(before)
        for n in (SYMS+'.cpp',SYMS+'.o'):after[n]['sha256']='b'
        self.assertEqual(len(changed_files(before,after)),2)
        after['eval.o']['sha256']='b'
        with self.assertRaisesRegex(ValueError,'non-observation'):changed_files(before,after)
        after['unexpected'] = dict(bytes=1,sha256='a')
        with self.assertRaisesRegex(ValueError,'creation'):changed_files(before,after)


LEAVES=[dict(path='TOP.a',width=1),dict(path='TOP.b',width=2)]


def stream(handles=(9,10),reverse=False):
    a,b=handles
    rows=['#FST\t0\t100\t-12\n',
          '#SIGNAL\ts000\t1\t%d\tTOP.a\n'%a,
          '#SIGNAL\ts001\t2\t%d\tTOP.b\n'%b]
    values=['0\t%d\t0\n'%a,'0\t%d\t00\n'%b]
    if reverse:values.reverse()
    return rows+values+['50\t%d\t1\n'%a,'50\t%d\t01\n'%b,'#END\n']


class Canonical(unittest.TestCase):
    def result(self,rows,leaves=LEAVES):
        output=io.BytesIO();report=canonicalize(iter(rows),leaves,output.write)
        return report,output.getvalue()

    def test_handle_and_cross_signal_serialization_normalization(self):
        a,bytes_a=self.result(stream());b,bytes_b=self.result(stream((110,17),True))
        self.assertEqual(bytes_a,bytes_b);self.assertEqual(a,b)

    def test_aliases_expand_and_widths_checked(self):
        leaves=[dict(path='TOP.a',width=1),dict(path='TOP.alias',width=1)]
        rows=['#FST\t0\t100\t-12\n','#SIGNAL\ts000\t1\t9\tTOP.a\n',
              '#SIGNAL\ts001\t1\t9\tTOP.alias\n','0\t9\t0\n','1\t9\t1\n','#END\n']
        result,data=self.result(rows,leaves);self.assertEqual(result['events'],4)
        self.assertIn(b'1\t1\t1\n',data)

    def test_same_tick_per_signal_order_and_repeats_retained(self):
        rows=stream();rows.insert(-1,'50\t9\t0\n');rows.insert(-1,'50\t9\t0\n')
        result,data=self.result(rows);self.assertEqual(result['events'],6)
        self.assertIn(b'50\t0\t1\n50\t0\t0\n50\t0\t0\n',data)

    def test_missing_clean_eof(self):
        with self.assertRaisesRegex(ValueError,'clean #END'):self.result(stream()[:-1])

    def test_chronology_and_unknown_handle(self):
        for replacement in ('-1\t9\t1\n','101\t9\t1\n','49\t9\t1\n','50\t99\t1\n'):
            rows=stream();rows.insert(-1,replacement)
            with self.assertRaises(ValueError):self.result(rows)

    def test_duplicate_or_missing_or_wrong_width_declaration(self):
        for change in ('duplicate','missing','width'):
            rows=stream()
            if change=='duplicate':rows.insert(3,rows[1])
            if change=='missing':rows.pop(2)
            if change=='width':rows[2]=rows[2].replace('\t2\t','\t3\t')
            with self.assertRaises(ValueError):self.result(rows)

    def test_missing_initialization_and_bad_value(self):
        rows=stream();rows=[r for r in rows if not r.startswith(('0\t10\t','50\t10\t'))]
        with self.assertRaisesRegex(ValueError,'initialized'):self.result(rows)
        rows=stream();rows[3]='0\t9\t10\n'
        with self.assertRaisesRegex(ValueError,'value/width'):self.result(rows)

    def test_data_after_end_rejected(self):
        with self.assertRaisesRegex(ValueError,'after clean EOF'):self.result(stream()+['0\t9\t1\n'])

    def test_exact_hierarchy_extra_or_missing_rejected(self):
        good='#VAR\t1\t9\tTOP.a\n#VAR\t2\t10\tTOP.b\n#END\n'
        declarations(good,LEAVES)
        with self.assertRaisesRegex(ValueError,'exact reviewed'):declarations(good.replace('#END','#VAR\t1\t11\tTOP.extra\n#END'),LEAVES)
        with self.assertRaises(ValueError):declarations(good.replace('#VAR\t1\t9\tTOP.a\n',''),LEAVES)

    def test_literal_gzip_comparison_and_payload_or_time_change(self):
        with tempfile.TemporaryDirectory() as folder:
            reports=[]
            for n,rows in enumerate((stream(),stream((20,31),True))):
                report,data=self.result(rows);p=Path(folder)/str(n)
                with gzip.open(p,'wb') as f:f.write(data)
                report['canonical_file']=dict(path=str(p));reports.append(report)
            equivalent(*reports)
            for mutate in ('payload','time'):
                other=copy.deepcopy(reports[1]);other['sha256']='bad'+mutate
                with self.assertRaisesRegex(ValueError,'event mismatch'):equivalent(reports[0],other)
            # Even forged equal metadata cannot hide changed canonical bytes.
            with gzip.open(reports[1]['canonical_file']['path'],'wb') as f:f.write(b'wrong')
            with self.assertRaisesRegex(ValueError,'byte stream'):equivalent(*reports)



if __name__=='__main__':unittest.main()
