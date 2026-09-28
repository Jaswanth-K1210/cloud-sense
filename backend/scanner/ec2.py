"""EC2 instances + ASG, security-group and target-group membership."""

import boto3

from backend.scanner.aws_session import owner_team, service_of, tags_to_dict
from backend.scanner.models import Resource


def _asg_membership(session: boto3.Session, region: str) -> dict[str, str]:
    client = session.client("autoscaling", region_name=region)
    out: dict[str, str] = {}
    for page in client.get_paginator("describe_auto_scaling_groups").paginate():
        for g in page["AutoScalingGroups"]:
            for inst in g.get("Instances", []):
                out[inst["InstanceId"]] = g["AutoScalingGroupName"]
    return out


def _target_groups(session: boto3.Session, region: str) -> dict[str, list[dict]]:
    """instance id -> [{arn, name, load_balancer_arns}]"""
    client = session.client("elbv2", region_name=region)
    out: dict[str, list[dict]] = {}
    for page in client.get_paginator("describe_target_groups").paginate():
        for tg in page["TargetGroups"]:
            if tg.get("TargetType", "instance") != "instance":
                continue
            info = {"arn": tg["TargetGroupArn"], "name": tg["TargetGroupName"],
                    "load_balancer_arns": tg.get("LoadBalancerArns", [])}
            health = client.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])
            for t in health["TargetHealthDescriptions"]:
                out.setdefault(t["Target"]["Id"], []).append(info)
    return out


def sg_references(session: boto3.Session, region: str) -> dict[str, list[str]]:
    """security group id -> SG ids its inbound rules allow traffic from."""
    client = session.client("ec2", region_name=region)
    out: dict[str, list[str]] = {}
    for page in client.get_paginator("describe_security_groups").paginate():
        for g in page["SecurityGroups"]:
            refs = {p["GroupId"] for perm in g.get("IpPermissions", []) for p in perm.get("UserIdGroupPairs", [])}
            refs.discard(g["GroupId"])
            out[g["GroupId"]] = sorted(refs)
    return out


def describe(session: boto3.Session, region: str, account_alias: str, account_id: str) -> list[Resource]:
    client = session.client("ec2", region_name=region)
    asgs = _asg_membership(session, region)
    tgs = _target_groups(session, region)
    out: list[Resource] = []
    for page in client.get_paginator("describe_instances").paginate():
        for resv in page["Reservations"]:
            for i in resv["Instances"]:
                state = i["State"]["Name"]
                if state in ("terminated", "shutting-down"):
                    continue
                iid = i["InstanceId"]
                tags = tags_to_dict(i.get("Tags"))
                attrs: dict = {
                    "security_groups": [g["GroupId"] for g in i.get("SecurityGroups", [])],
                    "volumes": [m["Ebs"]["VolumeId"] for m in i.get("BlockDeviceMappings", []) if "Ebs" in m],
                    "target_groups": tgs.get(iid, []),
                }
                if asg := asgs.get(iid) or tags.get("aws:autoscaling:groupName"):
                    attrs["asg"] = asg
                out.append(Resource(
                    id=iid,
                    arn=f"arn:aws:ec2:{region}:{account_id}:instance/{iid}",
                    account_alias=account_alias, region=region, type="ec2",
                    name=tags.get("Name", iid), tags=tags,
                    owner_team=owner_team(tags), service=service_of(tags),
                    state=state, instance_type=i.get("InstanceType"), created_at=i.get("LaunchTime"),
                    attrs=attrs,
                ))
    return out
