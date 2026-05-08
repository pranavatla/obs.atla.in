# Incident Playbooks

## Traffic Spike Scenario

Symptoms:
- Rapid increase in request volume
- p95 latency climbs above normal range
- Autoscaler events in service logs

Response:
- Verify ingress and API gateway saturation
- Scale stateless services horizontally
- Enable temporary rate limits for abusive clients
- Confirm error budget impact and recovery trend

## Database Error Burst

Symptoms:
- Elevated 5xx responses on checkout paths
- Query timeout messages from orders database
- Worker retries increasing queue depth

Response:
- Inspect DB connection pool and slow query profile
- Shift reads to cache where possible
- Apply retry/backoff and circuit-breaker policies
- Roll out schema/index fix and validate error-rate recovery
