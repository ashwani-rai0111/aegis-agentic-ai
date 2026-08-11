"""Thin boto3 helpers for CloudWatch, EC2, and SSM."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings, get_settings


class AwsConfigError(ValueError):
    pass


@lru_cache
def get_boto_session() -> boto3.session.Session:
    settings = get_settings()
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        raise AwsConfigError(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required for AWS tools"
        )
    return boto3.session.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def require_instance_id(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if not settings.aegis_ec2_instance_id:
        raise AwsConfigError("AEGIS_EC2_INSTANCE_ID is required for AWS tools")
    return settings.aegis_ec2_instance_id


def client(service: str):
    return get_boto_session().client(service)


def describe_alarm(alarm_name: str) -> dict[str, Any]:
    cw = client("cloudwatch")
    resp = cw.describe_alarms(AlarmNames=[alarm_name])
    alarms = resp.get("MetricAlarms") or []
    if not alarms:
        composite = resp.get("CompositeAlarms") or []
        if composite:
            alarm = composite[0]
            return {
                "alarm_name": alarm.get("AlarmName", alarm_name),
                "state": alarm.get("StateValue", "UNKNOWN"),
                "reason": alarm.get("StateReason", ""),
                "metric": "composite",
            }
        return {
            "alarm_name": alarm_name,
            "state": "NOT_FOUND",
            "reason": f"No CloudWatch alarm named '{alarm_name}'",
            "metric": None,
        }
    alarm = alarms[0]
    return {
        "alarm_name": alarm.get("AlarmName", alarm_name),
        "state": alarm.get("StateValue", "UNKNOWN"),
        "reason": alarm.get("StateReason", ""),
        "metric": alarm.get("MetricName"),
        "namespace": alarm.get("Namespace"),
        "dimensions": alarm.get("Dimensions", []),
    }


def get_metric_statistic(
    *,
    namespace: str,
    metric_name: str,
    dimensions: list[dict[str, str]] | None = None,
    period: int = 300,
    statistic: str = "Average",
) -> float | None:
    cw = client("cloudwatch")
    end = datetime.now(timezone.utc)
    start = end - timedelta(seconds=max(period * 3, 900))
    resp = cw.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=dimensions or [],
        StartTime=start,
        EndTime=end,
        Period=period,
        Statistics=[statistic],
    )
    points = sorted(resp.get("Datapoints") or [], key=lambda p: p["Timestamp"])
    if not points:
        return None
    return float(points[-1][statistic])


def describe_instance(instance_id: str) -> dict[str, Any]:
    ec2 = client("ec2")
    reservations = ec2.describe_instances(InstanceIds=[instance_id]).get(
        "Reservations", []
    )
    if not reservations or not reservations[0].get("Instances"):
        raise AwsConfigError(f"EC2 instance not found: {instance_id}")
    inst = reservations[0]["Instances"][0]
    status_resp = ec2.describe_instance_status(
        InstanceIds=[instance_id], IncludeAllInstances=True
    )
    statuses = status_resp.get("InstanceStatuses") or []
    system = instance = "unknown"
    if statuses:
        system = statuses[0].get("SystemStatus", {}).get("Status", "unknown")
        instance = statuses[0].get("InstanceStatus", {}).get("Status", "unknown")
    return {
        "instance_id": instance_id,
        "state": inst.get("State", {}).get("Name", "unknown"),
        "instance_type": inst.get("InstanceType"),
        "private_ip": inst.get("PrivateIpAddress"),
        "public_ip": inst.get("PublicIpAddress"),
        "status_checks": {"system": system, "instance": instance},
        "tags": {
            t.get("Key"): t.get("Value") for t in inst.get("Tags", []) if t.get("Key")
        },
    }


def ssm_run(
    commands: list[str],
    *,
    instance_id: str | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    instance_id = instance_id or require_instance_id(settings)
    timeout_seconds = timeout_seconds or settings.aegis_ssm_timeout_seconds
    ssm = client("ssm")
    try:
        send = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName=settings.aegis_ssm_document,
            Parameters={"commands": commands},
            TimeoutSeconds=timeout_seconds,
            Comment="Aegis agentic ops tool",
        )
    except (ClientError, BotoCoreError) as exc:
        return {
            "success": False,
            "error": str(exc),
            "stdout": "",
            "stderr": "",
            "instance_id": instance_id,
        }

    command_id = send["Command"]["CommandId"]
    deadline = time.time() + timeout_seconds
    last: dict[str, Any] = {}
    while time.time() < deadline:
        time.sleep(1.5)
        try:
            inv = ssm.get_command_invocation(
                CommandId=command_id, InstanceId=instance_id
            )
        except ClientError:
            continue
        last = inv
        status = inv.get("Status")
        if status in {"Success", "Cancelled", "TimedOut", "Failed", "Cancelling"}:
            break

    status = last.get("Status", "Unknown")
    return {
        "success": status == "Success",
        "status": status,
        "stdout": last.get("StandardOutputContent", "") or "",
        "stderr": last.get("StandardErrorContent", "") or "",
        "command_id": command_id,
        "instance_id": instance_id,
        "error": None if status == "Success" else (last.get("StatusDetails") or status),
    }
