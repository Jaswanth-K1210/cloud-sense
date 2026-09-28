"""Turns ground truth (trap archetypes + the env's critical resources) into human-like verdicts."""

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.candidates.rules import Candidate
from backend.scanner.models import Resource
from eval.sequence import Truth

REASONS = {
    "dr_standby": ["That's the DR standby for {dep}, it's idle on purpose.",
                   "Standby replica for disaster recovery. Idle by design, never stop it.",
                   "DR standby. Zero CPU is expected; it only takes traffic in a failover."],
    "payroll_batch": ["Payroll batch worker: average CPU is low but it spikes hard at month-end.",
                      "Month-end batch job. Don't rightsize based on averages.",
                      "This runs payroll at the end of the month; it needs the headroom."],
    "audit_archive": ["Audit archive under legal retention. Don't touch it without compliance.",
                      "Legal hold: archive data we must keep as is.",
                      "Compliance archive, retention is mandated by legal."],
    "blue_green": ["Blue/green standby, zero traffic is our rollback path.",
                   "That's the idle colour of our blue/green deploy. Keep it for rollback.",
                   "Rollback environment for blue/green. It's supposed to be idle."],
    "license_pinned": ["License-pinned host; the license forbids changing the instance type.",
                       "Our software license is tied to this instance size. Don't resize.",
                       "License host. Resizing breaks the license terms."],
    "oncall_debug": ["SRE on-call debug host. Idle until an incident, then we need it immediately.",
                     "On-call toolbox for SRE. Don't stop it.",
                     "Debug host owned by SRE for incidents."],
    "critical": ["Leave it: {note}.", "No, that's production-critical ({note}).", "Don't touch this one: {note}."],
}
APPROVALS = ["Yes, go ahead.", "Fine, it's unused.", "Approved, that's waste."]


@dataclass
class SimVerdict:
    decision: str
    reason: str
    scope: str = "similar"
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SimReviewer:
    id: str = "sim-engineer"
    name: str = "Sam (simulated)"
    team: str = "platform"


class SimulatedEngineer:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def review(self, cand: Candidate, res: Resource, truth: Truth | None) -> SimVerdict:
        if truth is None or truth.archetype is None:
            return SimVerdict("approve", self.rng.choice(APPROVALS), scope="this_resource")
        dep = res.depends_on_names[0] if res.depends_on_names else "the primary"
        text = self.rng.choice(REASONS[truth.archetype]).format(dep=dep, note=truth.note or "production")
        return SimVerdict("reject", text, scope="this_resource" if truth.archetype == "critical" else "similar")
