"""Host-only source-domain and producer-byte checks; no poll, launcher or vendor."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import prepare_packet

HERE=Path(__file__).resolve().parent

class Domains(unittest.TestCase):
    def test_only_unused_worker_repo_excluded_no_native_RTL_dropped(self):
        q=json.loads((HERE/'admission.DRAFT.json').read_text())['configuration']
        self.assertEqual(len(q['prepared_source_files']),5255)
        self.assertEqual(len(q['source_files']),4523)
        self.assertEqual(set(q['prepared_source_files'])-set(q['source_files']),{p for p in q['prepared_source_files'] if p.startswith('import/bsg_replicant/')})
        actual=json.loads(Path('/home/coyang/fpga-artifacts/context-resume/retained-borrow-trace0-fullcore-20261122/home-proof01/actual-source-list.json').read_text())
        prefix='/home/coyang/zynq-parrot-linux-borrow-profile/'
        native=[p[len(prefix):] for p in actual['sources'] if p.startswith(prefix)]
        self.assertEqual(len(native),392)
        self.assertTrue(set(native)<=set(q['source_files']))

    def test_regenerated_runtime_bytes_match_and_no_existing_packet_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'prepare_packet.py').write_bytes((HERE/'prepare_packet.py').read_bytes())
            old=prepare_packet.HERE;prepare_packet.HERE=root
            try:
                with contextlib.redirect_stdout(io.StringIO()):prepare_packet.main()
                for name in ('monitor_local.py','remote_probe.py','identity.py','budget.py'):
                    self.assertEqual((root/name).read_bytes(),(HERE/name).read_bytes(),name)
                with self.assertRaisesRegex(RuntimeError,'preserve any prior'):prepare_packet.main()
            finally:prepare_packet.HERE=old

    def test_source_bytes_and_symlink_modes_are_distinct(self):
        q=json.loads((HERE/'admission.DRAFT.json').read_text())['configuration'];q['job']='TEST_ONLY'
        spec=importlib.util.spec_from_file_location('test_only_probe',HERE/'remote_probe.py')
        m=importlib.util.module_from_spec(spec);m.CONFIG=q;spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'data';p.write_bytes(b'original');link=root/'link';link.symlink_to('data')
            self.assertEqual(m.source_record(p,{})['mode'],'100644')
            self.assertEqual(m.source_record(link,{})['mode'],'120000')
            self.assertNotEqual(m.source_record(link,{})['sha256'],m.source_record(p,{})['sha256'])
            before=m.source_record(p,{})['sha256'];p.write_bytes(b'corrupt')
            self.assertNotEqual(m.source_record(p,{})['sha256'],before)

if __name__=='__main__':unittest.main()
