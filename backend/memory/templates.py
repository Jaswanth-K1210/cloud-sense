"""Cold-start pack: 10 common exceptions a new org can accept (BUILD_DOC 5.9)."""

from typing import Any

from backend.memory.types import MemoryClientProtocol

TEMPLATES: dict[str, str] = {
    "dr-standby": "Disaster-recovery standbys and replicas (names with standby, replica or dr) are idle by design; "
                  "never stop or delete them for low utilization.",
    "month-end-batch": "Batch and payroll workers have low average CPU but spike at month-end or nightly; "
                       "never rightsize or stop them based on averages.",
    "legal-archive": "Audit and archive storage is kept for legal retention; never delete or tier it without "
                     "compliance sign-off.",
    "blue-green": "Blue/green standby environments carry zero traffic on purpose as the rollback path; "
                  "never stop them.",
    "license-pinned": "License-pinned hosts must keep their instance type; never rightsize them.",
    "on-call-debug": "On-call debug hosts are idle between incidents but owned by SRE; never stop them.",
    "ci-runners": "CI runners are idle outside builds; stopping is fine only if the runner autoscaler is aware.",
    "bastion": "Bastion hosts have near-zero traffic but are the emergency access path; never stop them.",
    "nat-instance": "NAT instances route private-subnet egress; low CPU is normal and stopping breaks the subnet.",
    "log-shipper": "Log shippers look idle but losing them loses audit logs; never stop them.",
}


async def seed_accepted(client: MemoryClientProtocol, org: Any, rule_ids: list[str]) -> list[str]:
    """Retain each accepted template as an org policy seed. Unknown ids are ignored."""
    accepted = [rid for rid in rule_ids if rid in TEMPLATES]
    for rid in accepted:
        await client.retain_seed(org, TEMPLATES[rid], doc_id=f"seed-{rid}")
    return accepted
