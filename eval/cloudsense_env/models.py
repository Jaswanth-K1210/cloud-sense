"""CloudSense Pydantic models — all data structures for the RL environment."""

from enum import Enum

from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    ec2 = "ec2"
    rds = "rds"
    s3 = "s3"
    load_balancer = "load_balancer"
    kubernetes = "kubernetes"
    nat_gateway = "nat_gateway"
    elasticsearch = "elasticsearch"
    ebs = "ebs"
    eip = "eip"


class Environment(str, Enum):
    prod = "prod"
    staging = "staging"
    dev = "dev"


class ActionType(str, Enum):
    rightsize_resource = "rightsize_resource"
    terminate_resource = "terminate_resource"
    add_lifecycle_policy = "add_lifecycle_policy"
    enable_autoscaling = "enable_autoscaling"
    purchase_reservation = "purchase_reservation"
    change_storage_class = "change_storage_class"
    schedule_uptime = "schedule_uptime"
    request_more_info = "request_more_info"
    skip_resource = "skip_resource"


class CloudResource(BaseModel):
    resource_id: str
    resource_type: ResourceType
    name: str
    environment: Environment
    region: str = "us-east-1"
    current_config: dict
    utilization: dict
    monthly_cost: float
    tags: dict = Field(default_factory=dict)
    has_backups: bool = False
    is_critical: bool = False
    dependencies: list[str] = Field(default_factory=list)
    usage_pattern: str = "always_on"
    subnet: str | None = None


class CloudAction(BaseModel):
    action_type: ActionType
    resource_id: str
    new_config: dict | None = None
    reasoning: str = ""


class CloudObservation(BaseModel):
    task_id: str
    goal: str
    account_id: str
    resources: list[dict]
    monthly_cost_current: float
    monthly_cost_optimized: float
    total_possible_savings: float
    actions_taken: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    step_number: int = 0
    max_steps: int = 10
    last_reward: float = 0.0
    last_action_error: str | None = None
    info: dict = Field(default_factory=dict)


class CloudReward(BaseModel):
    value: float = Field(ge=0.0, le=1.0)
    cost_saved: float = 0.0
    cost_reduction_pct: float = 0.0
    actions_correct: int = 0
    actions_dangerous: int = 0
    breakdown: dict = Field(default_factory=dict)
    done: bool = False


class StepResult(BaseModel):
    observation: CloudObservation
    reward: float
    done: bool
    info: dict = Field(default_factory=dict)
