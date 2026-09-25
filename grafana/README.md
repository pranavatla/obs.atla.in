# Grafana dashboards

Dashboards for Grafana Cloud, generated from one definition per site so every site is monitored
the same way. Edit `build_dashboards.py`, then regenerate:

```bash
python3 grafana/build_dashboards.py
```

| File | Shows |
|---|---|
| `dashboards/overview.json` | One line per site: status, uptime, check duration, requests, 5xx rate |
| `dashboards/atla-in.json` | atla.in: availability, real visitors (RUM), delivery, security (WAF), deploy markers |
| `dashboards/aif-atla-in.json` | aif.atla.in: availability, delivery |
| `dashboards/games-atla-in.json` | games.atla.in: availability, delivery |
| `dashboards/obs-atla-in.json` | obs.atla.in: availability, delivery |
| `dashboards/gita-atla-in.json` | gita.atla.in: availability, traffic (load balancer), AI (Bedrock calls, tokens, latency, errors, estimated cost) |

A site gets a section only when its data exists: Security needs an AWS WAF web ACL, Real visitors
needs a CloudWatch RUM app monitor, deploy markers need the site's deploy to post annotations.

## Import

Grafana → Dashboards → New → Import → upload the JSON (Overwrite if it exists), then pick the
CloudWatch and `grafanacloud-…-prom` data sources.

## Data sources

| Section | Source |
|---|---|
| Availability | Grafana Synthetic Monitoring checks named `<domain> homepage` (Prometheus) |
| Real visitors | CloudWatch `AWS/RUM`, `us-east-1` |
| Delivery | CloudWatch `AWS/CloudFront`, `us-east-1`, dimensions `DistributionId`, `Region=Global` |
| Security | CloudWatch `AWS/WAFV2`, `us-east-1` |
| Traffic (gita) | CloudWatch `AWS/ApplicationELB`, `ap-south-1`, found by load balancer name |
| AI (gita) | CloudWatch `AWS/Bedrock`, `ap-south-1`, by `ModelId`; cost = tokens × prices entered on the dashboard |
| Deploy markers | Grafana annotations tagged with the domain and `deploy` |

## CloudWatch access

The CloudWatch data source uses **Grafana Assume Role** with the IAM role
`GrafanaCloudCloudWatchRead`. Its trust policy allows only Grafana Cloud's AWS account with this
stack's external ID, and its inline policy allows only read-only CloudWatch metric calls. Log
access is deliberately not granted.

## Cost

Each panel refresh calls `GetMetricData` (about $0.01 per 1,000 metrics). Dashboards refresh
every 15 minutes at most; keep it that way.
