# Runbook: API High Latency

## Symptoms
- CloudWatch alarm on API p95 latency
- Elevated error/timeout rates
- Possible memory or swap pressure

## Investigation
1. Check CloudWatch latency, memory, swap, CPU
2. Inspect PM2 process health and restart counts
3. Review recent application logs for timeouts/GC pauses
4. Check database connection/memory pressure

## Preferred low-risk remediation
- If the `api` PM2 process is unhealthy and memory/latency are high:
  - Execute allowlisted action `restart_pm2_process` with `process_name=api`
  - Verify latency < 500ms and memory < 75%
  - Confirm alarm returns to OK

## Escalate if
- Remediation does not restore health
- Disk is full
- Action would require terminating instances or changing security groups