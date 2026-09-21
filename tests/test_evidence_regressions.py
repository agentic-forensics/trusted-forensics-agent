"""Adversarial evidence checks motivated by the review (companion A.2, A.5, D.3)."""
import copy
from dataclasses import replace
import unittest

from tfa.capability import check_call, check_episode, parse_certificate
from tfa.model import IntegrityStatus
from tfa.questions import (Classification, q2_which_model, q4_whose_identity,
                           q5_auto_approved)
from tfa.report import analyse
from tfa.synth import build_episode
from tfa.scenarios import build_cross_provider_episode


class EvidenceRegressions(unittest.TestCase):
    def setUp(self):
        self.ep = build_episode()
        self.tool = self.ep.span_by_id('span-tool-emailread')

    def test_root_identity_cannot_establish_acting_identity(self):
        spans = [replace(s, attributes={k: v for k, v in s.attributes.items()
                                      if k != 'auth.subject'})
                 if s.operation_name in ('execute_tool', 'downstream') else s
                 for s in self.ep.spans]
        answer = q4_whose_identity(spans)
        self.assertEqual(answer.classification, Classification.UNANSWERED_UNAVAILABLE)
        self.assertIsNotNone(answer.gap)

    def test_q4_reports_only_the_acting_identity(self):
        tool = replace(self.tool, attributes=dict(self.tool.attributes,
                                                **{'auth.subject': 'service-worker'}))
        root = self.ep.span_by_id('span-invoke-agent')
        answer = q4_whose_identity([root, tool])
        self.assertIn('service-worker', answer.value)
        self.assertNotIn('alice@acme.example', answer.value)
        self.assertEqual(answer.evidence, (tool.span_id,))

    def test_q2_includes_multiple_models_and_all_missing_parties(self):
        first = self.ep.span_by_id('span-inference-1')
        second = replace(first, span_id='model-2', attributes=dict(first.attributes,
                         **{'gen_ai.request.model': 'another-model'}))
        answer = q2_which_model([first, second])
        self.assertIn('another-model', answer.value)
        self.assertIn(first.get('gen_ai.request.model'), answer.value)
        self.assertIn('model-2', answer.evidence)

    def test_required_flag_is_not_approval(self):
        tool = replace(self.tool, attributes=dict(self.tool.attributes,
                       **{'dcfp.approval.required': True}))
        answer = q5_auto_approved([tool])
        self.assertEqual(answer.classification, Classification.UNANSWERED_UNAVAILABLE)
        self.assertIsNotNone(answer.gap)

    def approval_tool(self):
        return replace(self.tool, attributes=dict(self.tool.attributes, **{
            'dcfp.approval.required': True, 'dcfp.approval.mode': 'auto',
            'dcfp.approval.decision': 'approved', 'dcfp.approval.actor': 'policy-engine',
            'dcfp.approval.policy_id': 'triage', 'dcfp.approval.policy_version': '1',
        }))

    def test_positive_approval_reports_values(self):
        answer = q5_auto_approved([self.approval_tool()])
        self.assertEqual(answer.classification, Classification.ANSWERED_DIRECT)
        self.assertIn("mode='auto'", answer.value)
        self.assertIn("decision='approved'", answer.value)

    def test_unlinked_approval_does_not_answer_execution(self):
        unrelated = replace(self.approval_tool(), operation_name='inference')
        self.assertEqual(q5_auto_approved([unrelated, self.tool]).classification,
                         Classification.UNANSWERED_UNAVAILABLE)

    def test_one_approval_does_not_cover_other_calls(self):
        answer = q5_auto_approved([self.approval_tool(), self.ep.span_by_id('span-tool-emailsend')])
        self.assertEqual(answer.classification, Classification.PARTIAL)
        self.assertIn('span-tool-emailsend', answer.gap.note)

    def test_wrong_or_missing_agent_version_is_not_in_scope(self):
        cert = parse_certificate(next(iter(self.ep.capability_certificates.values())))
        for version in ['unapproved', None]:
            attrs = dict(self.tool.attributes)
            attrs.pop('gen_ai.agent.version')
            if version:
                attrs['gen_ai.agent.version'] = version
            result = check_call(cert, replace(self.tool, attributes=attrs))
            self.assertFalse(result.in_scope)
            self.assertIn('binding', result.failed_dimensions)

    def test_certificate_selection_is_not_dictionary_order(self):
        certs = copy.deepcopy(self.ep.capability_certificates)
        valid = next(iter(certs.values()))
        other = dict(valid, cert_id='other', agent_version='other-version', revoked=True)
        certs['other'] = other
        self.assertTrue(check_episode(certs, [self.tool])[0].in_scope)
        self.assertTrue(check_episode(dict(reversed(list(certs.items()))), [self.tool])[0].in_scope)

    def test_effect_derivation_binds_call_and_downstream_record(self):
        a = analyse(self.ep)
        effects = [e for e in a.graph.edges if e.edge_type.value == 'produced_effect_on']
        self.assertEqual(effects[0].source_artefact,
                         ('span-tool-emailsend', 'span-egress-http'))

    def test_unlinked_effect_does_not_make_a_graph_edge(self):
        from tfa.graph import build_graph
        self.ep.span_by_id('span-egress-http').attributes.pop('dcfp.effect.observed')
        self.assertFalse(any(e.edge_type.value == 'produced_effect_on'
                             for e in build_graph(self.ep.spans).edges))

    def test_graph_records_evidence_integrity(self):
        a = analyse(self.ep)
        self.assertTrue(all(e.integrity_status == IntegrityStatus.VERIFIED for e in a.graph.edges))

    def test_changed_content_changes_derivation_inputs_and_selftrace(self):
        before = analyse(self.ep)
        ep = copy.deepcopy(self.ep)
        ep.span_by_id('span-invoke-agent').attributes['gen_ai.input.messages'][0]['content'] = 'Changed goal'
        after = analyse(ep)
        def q1(a):
            return next(r for r in a.ledger.records() if r['output_id'] == 'answer-Q1')
        self.assertNotEqual(q1(before)['input_hashes'], q1(after)['input_hashes'])
        self.assertNotEqual(before.tracer.chain.head, after.tracer.chain.head)

    def test_changed_certificate_changes_capability_provenance(self):
        before = analyse(self.ep)
        next(iter(self.ep.capability_certificates.values()))['revoked'] = True
        after = analyse(self.ep)
        def inputs(a):
            return next(r['input_hashes'] for r in a.ledger.records()
                        if r['output_id'] == 'capability-span-tool-emailread')
        self.assertNotEqual(inputs(before), inputs(after))

    def test_mailbox_recipient_alone_does_not_invent_a_lead(self):
        for span in self.ep.spans:
            span.attributes.pop('dcfp.demo.lead', None)
        self.assertEqual(analyse(self.ep).unverified_leads, [])

    def test_unrelated_case_does_not_get_mailbox_lead(self):
        self.assertEqual(analyse(build_cross_provider_episode()).unverified_leads, [])


if __name__ == '__main__':
    unittest.main()
