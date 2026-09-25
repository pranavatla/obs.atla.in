# Grafana dashboards

Dashboards for Grafana Cloud, kept here so they are versioned and can be re-imported.

| File | Shows | Data source |
|---|---|---|
| `dashboards/atla-in-delivery.json` | CloudFront requests, error rates and bytes for atla.in (`E2OMRFTQ27WGMZ`) | CloudWatch |

## Import

Grafana → Dashboards → New → Import → upload the JSON, then pick the CloudWatch data source.

## CloudWatch access

The data source uses **Grafana Assume Role** with the IAM role
`GrafanaCloudCloudWatchRead`. Its trust policy allows only Grafana Cloud's AWS
account with this stack's external ID, and its inline policy allows only
read-only CloudWatch metric calls. Log access is deliberately not granted.

Set the data source's default region to `us-east-1`: CloudFront publishes its
metrics there, with dimensions `DistributionId` and `Region=Global`.

## Cost

Each panel refresh calls `GetMetricData` (about $0.01 per 1,000 metrics). The
dashboard refreshes every 15 minutes at most; keep it that way.
