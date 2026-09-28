"""Seed the cheapest possible demo estate in ONE region of a sandbox account.

    python infra/sandbox-seed/seed.py --region us-east-1 [--dry-run]
    python infra/sandbox-seed/seed.py --region us-east-1 --teardown

Everything created carries the tag cloudsense-demo=true; --teardown deletes exactly those.
Cost: 6 x t4g.nano (~$3/month each) + a few GiB of EBS + one idle EIP (~$3.65/month).
Seed several days before a demo so CloudWatch has history. Set a billing alarm (infra/billing-alarm.md).
"""

import argparse
import secrets

import boto3

DEMO_TAG = {"Key": "cloudsense-demo", "Value": "true"}
INSTANCE_TYPE = "t4g.nano"
AMI_PARAM = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"

# Month-end-style spikes, compressed to "once a day" so a week of history shows them.
SPIKE_USER_DATA = """#!/bin/bash
cat >/etc/systemd/system/payroll-spike.service <<'EOF'
[Service]
Type=oneshot
ExecStart=/usr/bin/timeout 1200 /usr/bin/sha256sum /dev/zero
EOF
cat >/etc/systemd/system/payroll-spike.timer <<'EOF'
[Timer]
OnCalendar=*-*-* 03:00:00
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload && systemctl enable --now payroll-spike.timer
"""

# name -> (tags, user_data)
INSTANCES = {
    "orders-api-1": ({"team": "orders", "service": "orders", "env": "prod"}, None),
    "orders-db": ({"team": "orders", "service": "orders", "env": "prod", "do_not_terminate": "true"}, None),
    "orders-db-standby": ({"team": "orders", "service": "orders", "env": "prod", "depends-on": "orders-db"}, None),
    "payroll-batch-worker": ({"team": "finance", "service": "payroll", "env": "prod"}, SPIKE_USER_DATA),
    "dev-sandbox-3": ({"team": "platform", "env": "dev"}, None),
    "ci-runner-old": ({"team": "platform", "service": "ci", "env": "dev", "created_by": "terraform"}, None),
}


def tag_list(tags: dict[str, str], name: str | None = None) -> list[dict[str, str]]:
    out = [{"Key": k, "Value": v} for k, v in tags.items()] + [DEMO_TAG]
    return out + ([{"Key": "Name", "Value": name}] if name else [])


def plan(bucket: str) -> list[str]:
    return ([f"instance {n} ({INSTANCE_TYPE}) tags={t}" for n, (t, _) in INSTANCES.items()] +
            ["volume legacy-gp2-data (1 GiB gp2, attached to orders-api-1)",
             "volume orphaned-scratch (1 GiB gp3, unattached)",
             "elastic ip (unassociated)",
             f"s3 bucket {bucket} with one small object"])


def seed(region: str, ami: str | None = None) -> dict[str, str]:
    ec2 = boto3.client("ec2", region_name=region)
    ami = ami or boto3.client("ssm", region_name=region).get_parameter(Name=AMI_PARAM)["Parameter"]["Value"]
    ids: dict[str, str] = {}
    for name, (tags, user_data) in INSTANCES.items():
        kw = {"UserData": user_data} if user_data else {}
        inst = ec2.run_instances(ImageId=ami, InstanceType=INSTANCE_TYPE, MinCount=1, MaxCount=1,
                                 TagSpecifications=[{"ResourceType": "instance", "Tags": tag_list(tags, name)}],
                                 **kw)["Instances"][0]
        ids[name] = inst["InstanceId"]
    az = ec2.describe_instances(InstanceIds=[ids["orders-api-1"]])["Reservations"][0]["Instances"][0][
        "Placement"]["AvailabilityZone"]
    ec2.get_waiter("instance_running").wait(InstanceIds=[ids["orders-api-1"]])
    gp2 = ec2.create_volume(AvailabilityZone=az, Size=1, VolumeType="gp2", TagSpecifications=[
        {"ResourceType": "volume", "Tags": tag_list({"team": "orders"}, "legacy-gp2-data")}])["VolumeId"]
    ec2.get_waiter("volume_available").wait(VolumeIds=[gp2])
    ec2.attach_volume(VolumeId=gp2, InstanceId=ids["orders-api-1"], Device="/dev/sdf")
    ids["legacy-gp2-data"] = gp2
    ids["orphaned-scratch"] = ec2.create_volume(AvailabilityZone=az, Size=1, VolumeType="gp3", TagSpecifications=[
        {"ResourceType": "volume", "Tags": tag_list({"team": "platform"}, "orphaned-scratch")}])["VolumeId"]
    ids["eip"] = ec2.allocate_address(Domain="vpc", TagSpecifications=[
        {"ResourceType": "elastic-ip", "Tags": tag_list({"team": "orders"}, "old-orders-ip")}])["AllocationId"]

    s3 = boto3.client("s3", region_name=region)
    bucket = f"audit-archive-{secrets.token_hex(4)}"
    kw = {} if region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": region}}
    s3.create_bucket(Bucket=bucket, **kw)
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": tag_list({"team": "security"})})
    s3.put_object(Bucket=bucket, Key="2025/q4/audit.log", Body=b"audit trail placeholder\n")
    ids["bucket"] = bucket
    return ids


def teardown(region: str) -> list[str]:
    ec2 = boto3.client("ec2", region_name=region)
    demo = [{"Name": "tag:cloudsense-demo", "Values": ["true"]}]
    done: list[str] = []
    inst = [i["InstanceId"] for r in ec2.describe_instances(Filters=demo + [
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}])["Reservations"]
            for i in r["Instances"]]
    if inst:
        ec2.terminate_instances(InstanceIds=inst)
        ec2.get_waiter("instance_terminated").wait(InstanceIds=inst)
        done += inst
    for v in ec2.describe_volumes(Filters=demo)["Volumes"]:
        if v["State"] == "in-use":
            ec2.detach_volume(VolumeId=v["VolumeId"], Force=True)
            ec2.get_waiter("volume_available").wait(VolumeIds=[v["VolumeId"]])
        ec2.delete_volume(VolumeId=v["VolumeId"])
        done.append(v["VolumeId"])
    for a in ec2.describe_addresses(Filters=demo)["Addresses"]:
        ec2.release_address(AllocationId=a["AllocationId"])
        done.append(a["AllocationId"])
    s3 = boto3.client("s3", region_name=region)
    for b in s3.list_buckets().get("Buckets", []):
        if not b["Name"].startswith("audit-archive-"):
            continue
        try:
            tags = s3.get_bucket_tagging(Bucket=b["Name"])["TagSet"]
        except s3.exceptions.ClientError:
            continue
        if DEMO_TAG in tags:
            for o in s3.list_objects_v2(Bucket=b["Name"]).get("Contents", []):
                s3.delete_object(Bucket=b["Name"], Key=o["Key"])
            s3.delete_bucket(Bucket=b["Name"])
            done.append(b["Name"])
    return done


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--dry-run", action="store_true", help="print what would be created and exit")
    p.add_argument("--teardown", action="store_true", help="delete everything tagged cloudsense-demo=true")
    p.add_argument("--ami", help="override the AMI (default: latest Amazon Linux 2023 arm64)")
    a = p.parse_args()
    if a.teardown:
        print("deleted:", *teardown(a.region), sep="\n  ")
    elif a.dry_run:
        print("would create:", *plan("audit-archive-<random>"), sep="\n  ")
    else:
        for name, rid in seed(a.region, a.ami).items():
            print(f"{name:22s} {rid}")
