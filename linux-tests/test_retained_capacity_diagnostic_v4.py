"""Offline SP-only approval separation and unchanged recovery/program checks."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import retained_capacity_diagnostic as original
import retained_capacity_diagnostic_v3 as v3
import retained_capacity_diagnostic_v4 as p
import run_retained_capacity_diagnostic_v3 as recovery
import run_retained_capacity_diagnostic_v4 as client

PREP=p.ROOT/'research/retained-capacity-sp-v4-20261121'
DRAFT=PREP/'prepared01/diagnostic.DRAFT.json'

def bridge_record():return json.loads(DRAFT.read_text())['candidate_bridge']


class Contract(unittest.TestCase):
    def test_actual_prepared_sp_proof_is_not_physical_approval(self):
        record=bridge_record();bridge=p.verify_prepared_sp(record)
        self.assertEqual(bridge['candidate'],p.SP_CANDIDATE);self.assertFalse(bridge['old_allslot_rerun_on_SP_model'])
        self.assertEqual(p.REVIEWED_CANDIDATE_BRIDGES,{})
        with self.assertRaisesRegex(ValueError,'no root-reviewed SP'):p.verify_candidate(dict(candidate_bridge=record))
    def test_M_AREA_bridge_rejected_even_if_entered_in_mock_allowlist(self):
        record=json.loads(Path(bridge_record()['path']).read_text())['historical']['M_AREA_bridge']
        with patch.object(p,'REVIEWED_CANDIDATE_BRIDGES',{record['sha256']:p.SP_CANDIDATE}):
            with self.assertRaisesRegex(ValueError,'exact independently prepared SP'):p.verify_candidate(dict(candidate_bridge=record))
    def test_SP_candidate_allowlist_is_independent_of_prepared_proof(self):
        record=bridge_record()
        with patch.object(p,'REVIEWED_CANDIDATE_BRIDGES',{record['sha256']:dict(p.SP_CANDIDATE,bp='0'*40)}):
            with self.assertRaisesRegex(ValueError,'separately reviewed exact SP'):p.verify_candidate(dict(candidate_bridge=record))
        # Only a test-local allowlist is injected, never a routed/deployable
        # admission. Actual route/package/MMIO checks remain a separate gate.
        with patch.object(p,'REVIEWED_CANDIDATE_BRIDGES',{record['sha256']:p.SP_CANDIDATE}):
            self.assertEqual(p.verify_candidate(dict(candidate_bridge=record)),p.SP_CANDIDATE)
    def test_exact_three_historical_capacity_programs_and_native_runners_unchanged(self):
        a=json.loads(DRAFT.read_text());p.verify_programs(a)
        self.assertIs(p.verify_programs,original.verify_programs);self.assertIs(p.parse_console,original.parse_console)
        self.assertEqual(p.ROLES,('d-enabled','d-off','i-enabled'));self.assertEqual(p.COUNTERS,original.COUNTERS)
        with self.assertRaises(ValueError):p.positive_use((0,0,0,0,0,0),'d')
    def test_SP_file_check_does_not_assume_M_evidence_schema(self):
        a=json.loads(DRAFT.read_text());a['artifacts']={};a['rollback_overlay']={}
        p.verify_files(a)
    def test_draft_refuses_before_reservation_output_or_commands(self):
        a=json.loads(DRAFT.read_text())
        with tempfile.TemporaryDirectory() as tmp,patch.object(p.base.maintained_session,'reservation') as lock:
            output=Path(tmp)/'never'
            with self.assertRaisesRegex(ValueError,'UNLAUNCHABLE'):client.execute(a,output)
            lock.assert_not_called();self.assertFalse(output.exists())
    def test_control_and_held_recovery_bodies_are_exact_V3(self):
        def node(module,name):
            path=Path(module.__file__);return ast.dump(next(x for x in ast.parse(path.read_text()).body if getattr(x,'name',None)==name))
        for name in ('Operations','request_recovery','execute'):self.assertEqual(node(client,name),node(recovery,name),name)
        for name in ('verify_route','validate'):self.assertEqual(node(p,name),node(v3,name),name)
    def test_all_V3_sources_and_RPC_remain_frozen_bound_inputs(self):
        before=json.loads((PREP/'dependency-manifest.json').read_text())
        self.assertEqual(before['v3_sources'],v3.source_hashes())
        self.assertEqual({k:p.source_hashes()[k] for k in v3.SOURCE_FILES},before['v3_sources'])
        self.assertIs(client.guard,recovery.guard);self.assertEqual(p.SCHEMA,'bp-retained-capacity-physical-diagnostic-v4-sp')


if __name__=='__main__':unittest.main()
