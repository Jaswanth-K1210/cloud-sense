"""The live demo moment: launch an UNTAGGED look-alike of orders-db-standby.

    python infra/sandbox-seed/launch_lookalike.py --region us-east-1

Only a Name tag (and the cloudsense-demo teardown tag): no team, service or purpose tags, so hard
directives can't catch it. CloudSense should suppress it anyway, citing the orders-db-standby rejection.
CloudWatch needs ~10-15 minutes of datapoints before the idle rule fires; set DEMO_LOOKBACK_HOURS=1 for the demo.
"""

import argparse

import boto3
from seed import AMI_PARAM, DEMO_TAG, INSTANCE_TYPE

NAME = "payments-db-standby"


def launch(region: str, ami: str | None = None) -> str:
    ami = ami or boto3.client("ssm", region_name=region).get_parameter(Name=AMI_PARAM)["Parameter"]["Value"]
    inst = boto3.client("ec2", region_name=region).run_instances(
        ImageId=ami, InstanceType=INSTANCE_TYPE, MinCount=1, MaxCount=1,
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": NAME}, DEMO_TAG]}])
    return inst["Instances"][0]["InstanceId"]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--ami")
    a = p.parse_args()
    print(f"{NAME} {launch(a.region, a.ami)}")
