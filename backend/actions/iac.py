"""IaC-managed resources are never mutated live: we hand back a Terraform diff for a pull request."""

import re

from backend.candidates.pricing import one_size_down
from backend.scanner.models import Resource

TF_TYPES = {"ec2": "aws_instance", "ebs": "aws_ebs_volume", "rds": "aws_db_instance", "eip": "aws_eip",
            "s3": "aws_s3_bucket", "snapshot": "aws_ebs_snapshot"}


def tf_address(res: Resource) -> str:
    if addr := res.tags.get("tf:address"):
        return addr
    local = re.sub(r"[^a-zA-Z0-9_]", "_", res.display_name).strip("_").lower() or "this"
    return f"{TF_TYPES.get(res.type, 'aws_resource')}.{local}"


def terraform_diff(action: str, res: Resource) -> str:
    addr = tf_address(res)
    header = f"# CloudSense: {action} on {res.display_name} ({res.id}) is IaC-managed; apply via PR.\n# {addr}\n"
    if action == "rightsize" and res.instance_type:
        new = one_size_down(res.instance_type)
        return header + f'-  instance_type = "{res.instance_type}"\n+  instance_type = "{new}"\n'
    if action == "modify_gp3":
        return header + '-  type = "gp2"\n+  type = "gp3"\n'
    if action == "stop" and res.type == "ec2":
        return header + (f'+resource "aws_ec2_instance_state" "{addr.split(".")[-1]}_stopped" {{\n'
                         f"+  instance_id = {addr}.id\n"
                         '+  state       = "stopped"\n+}\n')
    if action == "stop" and res.type == "rds":
        return header + "# RDS has no stopped state in Terraform; consider a snapshot + count = 0:\n+  count = 0\n"
    return header + "# Remove this resource (or set count = 0) after taking a final snapshot:\n+  count = 0\n"
