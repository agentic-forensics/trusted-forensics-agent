"""Capability certificate parsing and the call-granularity check (companion A.2, A.3).

A capability certificate C binds an agent id and version to the tools,
operations, arguments, targets and purposes it is permitted to invoke, and
records its issuer, validity period and revocation status (companion A.2).

An execute_tool span is in scope only if all of these hold together: the tool,
the operation, the arguments, the target and the stated purpose each fall within
C. Matching the tool name alone is insufficient (companion A.2, A.3). An
out-of-scope call is first-class evidence of boundary subversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Dict, List, Optional, Sequence, Tuple

from .model import Span


@dataclass(frozen=True)
class Permission:
    """One permitted capability within a certificate."""

    tool: str
    operations: Tuple[str, ...]
    targets: Tuple[str, ...]                 # glob patterns
    purposes: Tuple[str, ...]
    argument_constraints: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityCertificate:
    """A parsed capability certificate C (companion A.2)."""

    cert_id: str
    agent_id: str
    agent_version: str
    issuer: str
    valid_from: int
    valid_to: int
    revoked: bool
    permitted: Tuple[Permission, ...]

    def permission_for(self, tool: str) -> Optional[Permission]:
        for p in self.permitted:
            if p.tool == tool:
                return p
        return None


def parse_certificate(data: Dict) -> CapabilityCertificate:
    """Parse the mapping form of a certificate into a typed certificate."""
    permitted = tuple(
        Permission(
            tool=p["tool"],
            operations=tuple(p.get("operations", ())),
            targets=tuple(p.get("targets", ())),
            purposes=tuple(p.get("purposes", ())),
            argument_constraints=dict(p.get("argument_constraints", {})),
        )
        for p in data.get("permitted", [])
    )
    return CapabilityCertificate(
        cert_id=data["cert_id"],
        agent_id=data["agent_id"],
        agent_version=data["agent_version"],
        issuer=data["issuer"],
        valid_from=int(data["valid_from"]),
        valid_to=int(data["valid_to"]),
        revoked=bool(data.get("revoked", False)),
        permitted=permitted,
    )


@dataclass(frozen=True)
class CapabilityCheck:
    """The outcome of checking one execute_tool call against a certificate.

    in_scope is True only if every dimension holds together. failed_dimensions
    names the dimensions (tool, operation, target, purpose, arguments, binding,
    validity) that did not, so an out-of-scope call is explained, not merely
    flagged.
    """

    span_id: str
    tool: Optional[str]
    operation: Optional[str]
    target: Optional[str]
    purpose: Optional[str]
    in_scope: bool
    failed_dimensions: Tuple[str, ...]
    reason: str

    @property
    def boundary_subversion(self) -> bool:
        return not self.in_scope


def _argument_constraints_hold(
    constraints: Dict[str, str], arguments: Dict
) -> Tuple[bool, List[str]]:
    """Check argument constraints. Unknown constraint kinds fail closed."""
    failures: List[str] = []
    for key, expected in constraints.items():
        if key == "recipient_domain":
            recipient = str(arguments.get("to", ""))
            if not recipient.endswith("@" + expected):
                failures.append(f"recipient_domain != {expected}")
        else:
            # An unrecognised constraint cannot be shown to hold; fail closed.
            failures.append(f"unrecognised argument constraint '{key}'")
    return (not failures), failures


def check_call(cert: CapabilityCertificate, span: Span) -> CapabilityCheck:
    """Check a single execute_tool span at call granularity (companion A.2, A.3)."""
    tool = span.get("gen_ai.tool.name")
    operation = span.get("dcfp.tool.operation")
    target = span.get("dcfp.tool.target")
    purpose = span.get("dcfp.tool.purpose")
    arguments = span.get("gen_ai.tool.arguments") or {}

    failed: List[str] = []
    reasons: List[str] = []

    # Binding: the certificate must bind this agent id and version.
    agent_id = span.get("dcfp.agent.id") or span.get("gen_ai.agent.id")
    if agent_id and agent_id != cert.agent_id:
        failed.append("binding")
        reasons.append(f"certificate binds {cert.agent_id}, span agent is {agent_id}")

    # Validity and revocation.
    if cert.revoked:
        failed.append("validity")
        reasons.append("certificate is revoked")
    start = span.start_time
    if not (cert.valid_from <= start <= cert.valid_to):
        failed.append("validity")
        reasons.append("call falls outside the certificate validity window")

    permission = cert.permission_for(tool) if tool else None
    if permission is None:
        failed.append("tool")
        reasons.append(f"tool '{tool}' is not permitted by the certificate")
    else:
        if operation not in permission.operations:
            failed.append("operation")
            reasons.append(f"operation '{operation}' not permitted for '{tool}'")
        if not any(fnmatch(target or "", pat) for pat in permission.targets):
            failed.append("target")
            reasons.append(f"target '{target}' not within permitted targets")
        if permission.purposes and purpose not in permission.purposes:
            failed.append("purpose")
            reasons.append(f"purpose '{purpose}' not within permitted purposes")
        ok, arg_failures = _argument_constraints_hold(
            permission.argument_constraints, arguments
        )
        if not ok:
            failed.append("arguments")
            reasons.extend(arg_failures)

    in_scope = not failed
    reason = "in scope" if in_scope else "; ".join(reasons)
    # De-duplicate failed dimensions while preserving order.
    seen = []
    for d in failed:
        if d not in seen:
            seen.append(d)
    return CapabilityCheck(
        span_id=span.span_id,
        tool=tool,
        operation=operation,
        target=target,
        purpose=purpose,
        in_scope=in_scope,
        failed_dimensions=tuple(seen),
        reason=reason,
    )


def check_episode(
    certificates: Dict[str, Dict],
    spans: Sequence[Span],
) -> List[CapabilityCheck]:
    """Check every execute_tool span against the agent's certificate.

    Certificates are supplied in their mapping form (as synth.py produces them)
    and parsed here. A tool call whose agent has no certificate is reported as
    out of scope on the binding dimension.
    """
    by_agent: Dict[str, CapabilityCertificate] = {}
    for data in certificates.values():
        cert = parse_certificate(data)
        by_agent[cert.agent_id] = cert

    checks: List[CapabilityCheck] = []
    for span in spans:
        if span.operation_name != "execute_tool":
            continue
        agent_id = span.get("dcfp.agent.id") or span.get("gen_ai.agent.id")
        cert = by_agent.get(agent_id)
        if cert is None:
            checks.append(
                CapabilityCheck(
                    span_id=span.span_id,
                    tool=span.get("gen_ai.tool.name"),
                    operation=span.get("dcfp.tool.operation"),
                    target=span.get("dcfp.tool.target"),
                    purpose=span.get("dcfp.tool.purpose"),
                    in_scope=False,
                    failed_dimensions=("binding",),
                    reason=f"no capability certificate for agent '{agent_id}'",
                )
            )
            continue
        checks.append(check_call(cert, span))
    return checks


def boundary_subversions(checks: Sequence[CapabilityCheck]) -> List[CapabilityCheck]:
    """Return the out-of-scope calls: first-class boundary-subversion evidence."""
    return [c for c in checks if c.boundary_subversion]
