"""Package tampering, replay and CLI regressions (companion A.6, B Phase 7)."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tfa.bundle import (analyse_bundle, create_bundle, reproduce_bundle, verify_bundle)
from tfa.canon import canonical_json, digest_hex
from tfa.cli import main, SCENARIOS
from tfa.report import analyse, render_report
from tfa.synth import build_episode, default_witness


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.analysis = analyse(build_episode())
        self.bundle = create_bundle(self.analysis)

    def test_round_trip_and_reproduction_for_all_scenarios(self):
        for name, build in SCENARIOS.items():
            with self.subTest(scenario=name):
                bundle = json.loads(json.dumps(create_bundle(analyse(build()))))
                self.assertTrue(verify_bundle(bundle).ok)
                result = reproduce_bundle(bundle)
                self.assertTrue(result.ok, result.messages)

    def test_deterministic_and_does_not_mutate_analysis(self):
        head = self.analysis.tracer.chain.head
        ledger = self.analysis.ledger.records()
        self.assertEqual(self.bundle, create_bundle(self.analysis))
        self.assertEqual(head, self.analysis.tracer.chain.head)
        self.assertEqual(ledger, self.analysis.ledger.records())

    def test_verification_never_signs(self):
        witness = default_witness()
        with patch.object(witness, 'attest', side_effect=AssertionError('must not sign')):
            self.assertTrue(verify_bundle(self.bundle, witness).ok)

    def test_tampering_with_every_component_fails(self):
        mutations = {
            'report': lambda p: p.__setitem__('report', p['report'] + 'altered'),
            'certificate': lambda p: next(iter(p['evidence']['episode']['capability_certificates'].values())).__setitem__('revoked', True),
            'evidence': lambda p: p['evidence']['episode']['spans'][0]['attributes'].__setitem__('tampered', True),
            'answer': lambda p: p['analysis']['answers'][0].__setitem__('value', 'invented'),
            'graph': lambda p: p['analysis']['graph']['edges'][0].__setitem__('target', 'invented'),
            'ledger': lambda p: p['ledger'][0].__setitem__('rule', 'changed'),
            'selftrace': lambda p: p['selftrace']['spans'][0]['attributes'].__setitem__('changed', True),
            'code': lambda p: p['code_manifest'].__setitem__('report.py', '0' * 64),
            'missing_segment': lambda p: p['evidence']['episode']['missing_segments'].append({'party': 'invented'}),
        }
        for name, change in mutations.items():
            with self.subTest(component=name):
                b = copy.deepcopy(self.bundle)
                change(b['payload'])
                self.assertFalse(verify_bundle(b).ok)

    def test_recalculating_manifest_does_not_repair_seal(self):
        self.bundle['payload']['report'] += 'altered'
        self.bundle['manifest']['report'] = digest_hex(canonical_json(self.bundle['payload']['report']))
        result = verify_bundle(self.bundle)
        self.assertFalse(result.ok)
        self.assertIn('package seal does not verify', result.messages)

    def test_removed_terminal_anchor_and_rehashed_manifest_still_fail(self):
        self.bundle['payload']['evidence']['anchors'].pop()
        self.bundle['manifest']['evidence'] = digest_hex(canonical_json(self.bundle['payload']['evidence']))
        self.assertFalse(verify_bundle(self.bundle).ok)

    def test_import_uses_original_receipts_and_anchors(self):
        with patch('tfa.report.witness_episode', side_effect=AssertionError('no recapture')):
            a = analyse_bundle(self.bundle)
        self.assertEqual(render_report(a), self.bundle['payload']['report'])
        self.assertEqual(a.chain.store.records(), self.bundle['payload']['evidence']['receipts'])
        self.assertEqual([x.as_record() for x in a.anchors], self.bundle['payload']['evidence']['anchors'])

    def test_invalid_bundle_is_not_analysed(self):
        self.bundle['payload']['report'] += 'changed'
        with self.assertRaises(ValueError):
            analyse_bundle(self.bundle)

    def test_manifest_component_removal_fails(self):
        del self.bundle['payload']['ledger']
        del self.bundle['manifest']['ledger']
        self.assertFalse(verify_bundle(self.bundle).ok)

    def test_false_independence_claim_fails(self):
        self.bundle['seal']['independent'] = True
        self.assertFalse(verify_bundle(self.bundle).ok)

    def test_malformed_bundles_fail_closed(self):
        for invalid in [None, [], {}, {'format': 'unknown'}]:
            with self.subTest(value=invalid):
                self.assertFalse(verify_bundle(invalid).ok)

    def test_new_code_can_verify_but_reproduction_requires_recorded_source(self):
        with patch('tfa.bundle.code_manifest', return_value={'different.py': '0' * 64}):
            self.assertTrue(verify_bundle(self.bundle).ok)
            self.assertFalse(reproduce_bundle(self.bundle).ok)

    def test_rendered_report_hash_is_recorded_in_selftrace(self):
        payload = self.bundle['payload']
        report_record = payload['ledger'][-1]
        self.assertEqual(report_record['output_id'], 'report')
        self.assertEqual(report_record['output_hash'], digest_hex(canonical_json(payload['report'])))
        self.assertEqual(payload['selftrace']['spans'][-1]['attributes']['dcfp.tfa.action'], 'render_report')


class BundleCliTests(unittest.TestCase):
    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = main(args)
        return result, out.getvalue(), err.getvalue()

    def test_export_import_views_verify_and_tamper(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'case.json'
            self.assertEqual(self.run_cli(['--bundle', str(path), '--demo-step', '4'])[0], 0)
            for step in range(1, 5):
                rc, text, _ = self.run_cli(['--from-bundle', str(path), '--demo-step', str(step)])
                self.assertEqual(rc, 0)
                self.assertIn(str(step) + ' /', text)
            self.assertEqual(self.run_cli(['--verify-bundle', str(path)])[0], 0)
            self.assertEqual(self.run_cli(['--reproduce', str(path)])[0], 0)
            b = json.loads(path.read_text())
            b['payload']['report'] += ' changed'
            path.write_text(json.dumps(b))
            self.assertEqual(self.run_cli(['--verify-bundle', str(path)])[0], 1)
            self.assertEqual(self.run_cli(['--from-bundle', str(path)])[0], 1)

    def test_report_cannot_overwrite_preserved_input(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'case.json'
            self.assertEqual(self.run_cli(['--bundle', str(path)])[0], 0)
            original = path.read_bytes()
            self.assertNotEqual(self.run_cli(['--from-bundle', str(path), '--out', str(path)])[0], 0)
            self.assertEqual(original, path.read_bytes())

    def test_existing_bundle_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'case.json'
            path.write_text('original')
            rc, _, _ = self.run_cli(['--bundle', str(path)])
            self.assertNotEqual(rc, 0)
            self.assertEqual(path.read_text(), 'original')

    def test_json_exposes_answers_graph_and_sources(self):
        rc, text, _ = self.run_cli(['--format', 'json'])
        self.assertEqual(rc, 0)
        result = json.loads(text)
        self.assertIn('answer', result['questions'][0])
        self.assertTrue(result['reconstruction']['graph']['edges'][0]['source_artefact'])

    def test_mermaid_exposes_graph_and_missing_provider(self):
        rc, text, _ = self.run_cli(['--scenario', 'cross', '--format', 'mermaid'])
        self.assertEqual(rc, 0)
        self.assertIn('flowchart LR', text)
        self.assertIn('MISSING: Provider-B', text)


if __name__ == '__main__':
    unittest.main()
