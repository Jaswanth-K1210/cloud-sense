import sys
from pathlib import Path

import boto3
from moto import mock_aws

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "infra" / "sandbox-seed"))
import launch_lookalike  # noqa: E402
import seed  # noqa: E402

REGION = "us-east-1"


def test_seed_then_teardown_removes_everything() -> None:
    with mock_aws():
        ec2 = boto3.client("ec2", region_name=REGION)
        ami = ec2.describe_images(Owners=["amazon"])["Images"][0]["ImageId"]
        # a resource that is NOT part of the demo must survive teardown
        keep = ec2.run_instances(ImageId=ami, MinCount=1, MaxCount=1)["Instances"][0]["InstanceId"]

        ids = seed.seed(REGION, ami=ami)
        look = launch_lookalike.launch(REGION, ami=ami)
        assert set(seed.INSTANCES) <= set(ids)
        tags = {i["InstanceId"]: {t["Key"]: t["Value"] for t in i.get("Tags", [])}
                for r in ec2.describe_instances()["Reservations"] for i in r["Instances"]}
        assert tags[ids["orders-db"]]["do_not_terminate"] == "true"
        assert tags[ids["ci-runner-old"]]["created_by"] == "terraform"
        assert set(tags[look]) == {"Name", "cloudsense-demo"}  # untagged look-alike

        deleted = seed.teardown(REGION)
        assert ids["bucket"] in deleted and ids["eip"] in deleted and look in deleted
        live = {i["InstanceId"] for r in ec2.describe_instances(Filters=[
            {"Name": "instance-state-name", "Values": ["running", "pending"]}])["Reservations"] for i in r["Instances"]}
        assert live == {keep}
        assert ec2.describe_volumes(Filters=[{"Name": "tag:cloudsense-demo", "Values": ["true"]}])["Volumes"] == []
