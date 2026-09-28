"""Base task class for CloudSense tasks."""

import json
from abc import ABC, abstractmethod
from pathlib import Path

from eval.cloudsense_env.models import ActionType, CloudResource

DATA_DIR = Path(__file__).parent.parent / "data"


class BaseTask(ABC):
    task_id: str
    difficulty: str
    max_steps: int
    description: str
    data_file: str
    optimal_cost: float

    @abstractmethod
    def get_correct_actions(self) -> dict[str, ActionType]:
        """Returns mapping of resource_id -> correct action type."""

    @abstractmethod
    def get_critical_resources(self) -> set[str]:
        """Resources that should be SKIPPED (prod, critical)."""

    @abstractmethod
    def get_action_savings(self) -> dict[str, float]:
        """resource_id -> expected $ savings if correct action taken."""

    def load_account(self) -> list[CloudResource]:
        """Load and return resources from JSON file."""
        path = DATA_DIR / self.data_file
        with open(path) as f:
            data = json.load(f)
        return [CloudResource(**r) for r in data]

    def load_account_raw(self) -> list[dict]:
        """Load raw dict data from JSON file."""
        path = DATA_DIR / self.data_file
        with open(path) as f:
            return json.load(f)
