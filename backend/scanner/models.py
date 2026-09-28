"""Resource model produced by both the real AWS scanner and the eval env adapter."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

# Candidate-bearing types first; the rest exist as graph nodes (blast radius only).
ResourceType = Literal["ec2", "ebs", "snapshot", "eip", "rds", "s3", "lb", "target_group", "asg", "nat", "eks",
                       "opensearch"]


class ResourceMetrics(BaseModel):
    cpu_avg: float | None = None
    cpu_max: float | None = None
    cpu_p95: float | None = None
    net_in_mb_per_day: float | None = None
    net_out_mb_per_day: float | None = None
    db_connections_max: float | None = None
    daily_cpu_series: list[float] = Field(default_factory=list)


def is_iac_managed(tags: dict[str, str]) -> bool:
    return tags.get("created_by", "").lower() == "terraform" or any(k.startswith("aws:cloudformation:") for k in tags)


class Resource(BaseModel):
    id: str
    arn: str = ""
    account_alias: str = ""
    region: str = "us-east-1"
    type: ResourceType
    name: str = ""
    tags: dict[str, str] = Field(default_factory=dict)
    owner_team: str | None = None
    service: str | None = None
    state: str = "unknown"
    instance_type: str | None = None
    volume_type: str | None = None
    size_gb: float | None = None
    created_at: datetime | None = None
    metrics: ResourceMetrics = Field(default_factory=ResourceMetrics)
    depends_on: list[str] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)
    role_hints: list[str] = Field(default_factory=list)
    # Type-specific facts: attached_to, replica_source, asg, security_groups, target_groups,
    # lifecycle_configured, associated_to, source_volume, used_by_ami, ...
    attrs: dict[str, Any] = Field(default_factory=dict)
    # Filled in by backend.graph.build from ids above.
    depends_on_names: list[str] = Field(default_factory=list)
    dependent_names: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def iac_managed(self) -> bool:
        return is_iac_managed(self.tags)

    @property
    def neighbor_names(self) -> list[str]:
        return list(dict.fromkeys(self.depends_on_names + self.dependent_names))

    @property
    def display_name(self) -> str:
        return self.name or self.id
