"""Task registry — maps task_id strings to task classes."""

from eval.cloudsense_env.tasks.task_easy import StartupCleanupTask
from eval.cloudsense_env.tasks.task_hard import EnterpriseFinOpsTask
from eval.cloudsense_env.tasks.task_medium import MidSizeAuditTask

TASKS = {
    "startup-cleanup": StartupCleanupTask,
    "mid-size-audit": MidSizeAuditTask,
    "enterprise-finops": EnterpriseFinOpsTask,
}
