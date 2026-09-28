from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from moto import mock_aws

from backend.scanner import metrics
from backend.scanner.scan import scan_account

REGION = "us-east-1"


@dataclass
class Acct:
    alias: str = "sandbox"
    aws_account_id: str = "123456789012"
    role_arn: str = "local"
    external_id: str = "x"
    regions: list = field(default_factory=lambda: [REGION])


def _ami(ec2) -> str:
    return ec2.describe_images(Owners=["amazon"])["Images"][0]["ImageId"]


@pytest.fixture
def estate():
    with mock_aws():
        ec2 = boto3.client("ec2", region_name=REGION)
        ami = _ami(ec2)
        tag = lambda n, **t: [{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": n},  # noqa: E731
                                                                   *[{"Key": k, "Value": v} for k, v in t.items()]]}]
        i1 = ec2.run_instances(ImageId=ami, MinCount=1, MaxCount=1, InstanceType="t3.micro",
                               TagSpecifications=tag("orders-api-1", team="orders", service="orders"))
        i2 = ec2.run_instances(ImageId=ami, MinCount=1, MaxCount=1, InstanceType="t3.large",
                               TagSpecifications=tag("dev-sandbox-3"))
        iid1 = i1["Instances"][0]["InstanceId"]
        az = i1["Instances"][0]["Placement"]["AvailabilityZone"]
        attached = ec2.create_volume(AvailabilityZone=az, Size=8, VolumeType="gp3")["VolumeId"]
        ec2.attach_volume(VolumeId=attached, InstanceId=iid1, Device="/dev/sdf")
        unattached = ec2.create_volume(AvailabilityZone=az, Size=10, VolumeType="gp3")["VolumeId"]
        gp2 = ec2.create_volume(AvailabilityZone=az, Size=5, VolumeType="gp2")["VolumeId"]
        eip = ec2.allocate_address(Domain="vpc")["AllocationId"]
        boto3.client("rds", region_name=REGION).create_db_instance(
            DBInstanceIdentifier="orders-db", DBInstanceClass="db.t3.micro", Engine="postgres",
            MasterUsername="u", MasterUserPassword="password123", AllocatedStorage=20)
        boto3.client("s3", region_name=REGION).create_bucket(Bucket="audit-archive-test")
        yield {"i1": iid1, "i2": i2["Instances"][0]["InstanceId"], "attached": attached,
               "unattached": unattached, "gp2": gp2, "eip": eip}


def test_scan_account_finds_everything(estate) -> None:
    res = {r.id: r for r in scan_account(Acct())}
    assert res[estate["i1"]].type == "ec2"
    assert res[estate["i1"]].name == "orders-api-1"
    assert res[estate["i1"]].owner_team == "orders"
    assert res[estate["i1"]].service == "orders"
    assert res[estate["i2"]].instance_type == "t3.large"
    assert res[estate["attached"]].attrs["attached_to"] == estate["i1"]
    assert res[estate["unattached"]].state == "available"
    assert res[estate["unattached"]].attrs["attached_to"] is None
    assert res[estate["gp2"]].volume_type == "gp2"
    assert res[estate["eip"]].type == "eip"
    assert res[estate["eip"]].state == "unassociated"
    assert res["orders-db"].type == "rds"
    assert res["orders-db"].instance_type == "db.t3.micro"
    assert res["audit-archive-test"].type == "s3"
    assert res["audit-archive-test"].attrs["lifecycle_configured"] is False
    assert all(r.account_alias == "sandbox" for r in res.values())


class FakeCW:
    """Returns two pages to exercise NextToken; records calls."""

    def __init__(self, points: dict[str, list[tuple[datetime, float]]]):
        self.points, self.calls = points, []

    def get_metric_data(self, **kw):
        self.calls.append(kw)
        ids = [q["Id"] for q in kw["MetricDataQueries"]]
        results = [{"Id": i, "Timestamps": [t for t, _ in self.points.get(i, [])],
                    "Values": [v for _, v in self.points.get(i, [])]} for i in ids]
        if "NextToken" not in kw:
            return {"MetricDataResults": results[:1], "NextToken": "t"}
        return {"MetricDataResults": results[1:]}


def test_fetch_batches_500_and_follows_next_token() -> None:
    queries = [{"Id": f"q{i}"} for i in range(1001)]
    cw = FakeCW({})
    metrics.fetch(cw, queries, datetime.now(UTC), datetime.now(UTC))
    assert [len(c["MetricDataQueries"]) for c in cw.calls] == [500, 500, 500, 500, 1, 1]


def test_aggregate_cpu_network_connections() -> None:
    t0 = datetime(2026, 9, 1, tzinfo=UTC)
    cpu = [(t0 + timedelta(hours=h), 2.0) for h in range(48)]
    cpu[30] = (cpu[30][0], 90.0)  # one spike on day 2
    m = metrics.aggregate({
        "cpu": cpu,
        "net_in": [(t0, 2e6), (t0, 2e6)],
        "net_out": [(t0, 1e6)],
        "conns": [(t0, 0.0), (t0, 3.0)],
    }, days=2)
    assert m.cpu_max == 90.0
    assert m.cpu_avg == pytest.approx((47 * 2 + 90) / 48)
    assert m.cpu_p95 < 90.0
    assert len(m.daily_cpu_series) == 2
    assert m.daily_cpu_series[0] == 2.0
    assert m.net_in_mb_per_day == pytest.approx(2.0)
    assert m.net_out_mb_per_day == pytest.approx(0.5)
    assert m.db_connections_max == 3.0


def test_build_queries_only_for_known_types() -> None:
    from backend.scanner.models import Resource

    q, idx = metrics.build_queries([Resource(id="i-1", type="ec2"), Resource(id="db", type="rds"),
                                    Resource(id="v", type="ebs")])
    assert len(q) == 5
    assert {f for _, f in idx.values()} == {"cpu", "net_in", "net_out", "conns"}
