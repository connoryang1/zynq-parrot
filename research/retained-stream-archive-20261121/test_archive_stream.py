#!/usr/bin/env python3
"""Host-only archive semantics and fail-closed counter-adapter checks."""
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import archive_stream as a

CHECKER = Path('/home/coyang/zynq-parrot-retained-observation/testing/rtl/retained-capacity-fixture/check_counter_words.py')


def tiny_stream():
    return (b'#FST\t0\t10\t-12\n'
            b'#SIGNAL\tobs.hits\t32\t1\tx.hits\n'
            b'#SIGNAL\tobs.published\t32\t2\tx.published\n'
            b'#SIGNAL\tobs.beats\t32\t3\tx.beats\n'
            b'#SIGNAL\tpayload\t8\t4\tx.payload\n'
            b'0\t1\t00000000000000000000000000000000\n'
            b'0\t2\t00000000000000000000000000000000\n'
            b'0\t3\t00000000000000000000000000000000\n'
            b'0\t4\t10101010\n#END\n')


class ArchiveTests(unittest.TestCase):
    def collect(self, raw, status=0):
        saved = io.BytesIO()
        traced = a.FullStream(io.BytesIO(raw), saved)
        observed = ''.join(traced)
        return observed, saved.getvalue(), traced.finish(status)

    def test_exact_serialized_semantics_normalize_integer_object_keys_only(self):
        self.assertEqual(a.semantic_bytes({'x':{12:[1,2]}}), a.semantic_bytes({'x':{'12':[1,2]}}))
        self.assertNotEqual(a.semantic_bytes({'x':{12:[1,2]}}), a.semantic_bytes({'x':{'12':[1,3]}}))

    def test_all_original_bytes_reach_consumer(self):
        observed, projection, digest = self.collect(tiny_stream())
        self.assertEqual(observed.encode(), tiny_stream())
        self.assertNotIn(b'payload', projection)
        self.assertNotIn(b'0\t4\t', projection)
        self.assertEqual(digest['bytes'], len(tiny_stream()))
        self.assertEqual(digest['sha256'], a.hashlib.sha256(tiny_stream()).hexdigest())
        self.assertEqual(digest['events'], 4)
        self.assertEqual(digest['counter_events'], 3)
        self.assertTrue(projection.endswith(b'#END\n'))

    def test_missing_and_duplicate_eof_rejected(self):
        for raw in (tiny_stream().replace(b'#END\n', b''), tiny_stream()+b'#END\n'):
            with self.assertRaises(ValueError): self.collect(raw)

    def test_failed_reader_even_after_complete_stream(self):
        with self.assertRaisesRegex(ValueError, 'completed0'):
            self.collect(tiny_stream(), 7)

    def test_actual_completion_callback_and_finish_exception_propagate(self):
        traced=a.FullStream(io.BytesIO(tiny_stream()),io.BytesIO())
        list(traced);called=[]
        self.assertEqual(traced.finish(lambda:called.append(True) or 0)['reader_returncode'],0)
        self.assertEqual(called,[True])
        class Validator:
            def sample(self,*args):pass
            def finish(self):raise ValueError('unfinished protocol owner')
        def edges(lines,selected):
            for line in lines:pass
            return iter(())
        with self.assertRaisesRegex(ValueError,'unfinished protocol owner'):
            a.validate_complete(io.BytesIO(tiny_stream()),io.BytesIO(),{},Validator(),edges,0)

    def test_projection_keeps_unknown_and_all_counter_transitions(self):
        raw = tiny_stream().replace(b'0\t1\t'+b'0'*32, b'0\t1\t'+b'x'*32)
        _, projection, _ = self.collect(raw)
        self.assertIn(b'x'*32, projection)

    def test_noncounter_corruption_still_reaches_validator(self):
        class Validator:
            def sample(self, t, clocks, values):
                a.require(values['payload'] == 170, 'full payload mismatch')
            def finish(self): return {'validated': True}
        def edges(lines, selected):
            for line in lines:
                fields=line.rstrip().split('\t')
                if len(fields)==3 and fields[1]=='4':
                    yield 0, [], {'payload':int(fields[2],2)}
        for raw, fails in ((tiny_stream(),False), (tiny_stream().replace(b'10101010',b'10101011'),True)):
            if fails:
                with self.assertRaisesRegex(ValueError,'payload mismatch'):
                    a.validate_complete(io.BytesIO(raw),io.BytesIO(),{},Validator(),edges,0)
            else:
                proof,_=a.validate_complete(io.BytesIO(raw),io.BytesIO(),{},Validator(),edges,0)
                self.assertEqual(proof,{'validated':True})

    def test_unchanged_counter_checker_rejects_bit_and_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            run=root/'run.json';a.write_json(run,{'counters':[0]*6})
            _, projection, _=self.collect(tiny_stream())
            for name, data, passed in (
                ('good',projection,True),
                ('bit',projection.replace(b'0\t1\t'+b'0'*32,b'0\t1\t'+b'0'*31+b'1'),False),
                ('unknown',projection.replace(b'0\t1\t'+b'0'*32,b'0\t1\t'+b'x'*32),False),
                ('prefix',projection.replace(b'#END\n',b''),False)):
                out=root/name;out.mkdir()
                events=out/'projection.gz'
                with gzip.open(events,'wb') as f:f.write(data)
                a.write_json(out/'verification.json',{'bindings':{'events':a.bind(events),'run':a.bind(run)}})
                p=subprocess.run([sys.executable,str(CHECKER),'--audit',str(out),'--out',str(out/'checked.json')],
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=10)
                self.assertEqual(p.returncode==0,passed,p.stdout.decode())
                self.assertEqual((out/'checked.json').exists(),passed)

    def test_chain_rejects_mutated_projection_and_rebound_wrong_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);adapter=out/'counter-check-input';adapter.mkdir()
            run=out/'run.json';a.write_json(run,{'counters':[0]*6})
            fst=out/'raw.fst';fst.write_bytes(b'inert fixture binding only')
            original=out/'original.json';semantic={'state':'host fixture only','targets':{'1':[2]}}
            a.write_json(original,dict(semantic,bindings={}))
            projection=out/'gp0-counter-projection.tsv.gz'
            with gzip.open(projection,'wb') as f:f.write(b'#END\n')
            full=dict(semantic,bindings={'run':a.bind(run),'fst':a.bind(fst)},archive={
                'counter_projection':a.bind(projection),'full_stream':{'reader_returncode':0,'exact_end_records':1},
                'semantic_sha256':a.hashlib.sha256(a.semantic_bytes(semantic)).hexdigest()})
            a.write_json(out/'verification.json',full)
            def receipts(wrong=False):
                a.write_json(adapter/'verification.json',{'schema':'counter-projection-input-only-v1',
                    'full_audit':a.bind(original if wrong else out/'verification.json'),
                    'bindings':{'run':a.bind(run),'events':a.bind(projection)}})
                a.write_json(out/'counter-words.json',{'audit':a.bind(adapter/'verification.json'),
                    'run':a.bind(run),'events':a.bind(projection),'auditor':a.bind(CHECKER)})
                a.write_json(out/'acceptance.json',{'schema':'complete167-counter-projection-qualification-v1',
                    'semantic_equality':True,'original_audit':a.bind(original),
                    'input_bindings':[a.bind(original),a.bind(fst)],'sources':[a.bind(CHECKER)],
                    'files':[a.bind(p) for p in (out/'verification.json',adapter/'verification.json',out/'counter-words.json',projection)]})
            receipts();a.check_chain(out)
            projection.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'binding changed'):a.check_chain(out)
            # Even updating all individual file hashes cannot redirect the adapter
            # away from its complete audit without violating the explicit chain.
            receipts(wrong=True)
            with self.assertRaisesRegex(ValueError,'adapter to complete audit chain'):a.check_chain(out)

    def test_resource_breach_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(a.shutil,'disk_usage',return_value=type('Usage',(),{'free':0})()):
                with self.assertRaisesRegex(ValueError,'reserve'):
                    a.resource_guard(Path(td),a.time.monotonic(),600)


if __name__=='__main__':
    unittest.main()
