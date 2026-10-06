# LangSmith Integration with gate.atla.in

This guide walks through setting up LangSmith trace collection and visualization in Grafana.

## What You're Setting Up

- **Trace Storage**: LangSmith traces synced to Postgres every 5 minutes
- **Grafana Dashboard**: Real-time visualization of latency, cost, and trace data
- **Alert Linking**: Alerts in Grafana link directly to LangSmith traces
- **Correlations**: Gateway audit events linked to LangSmith input/output data

## Prerequisites

- ✅ LangSmith API key (from https://smith.langchain.com)
- ✅ Postgres database (same as gate.atla.in uses)
- ✅ Grafana with Postgres datasource configured
- ✅ systemd for scheduling (or cron alternative)

## Step 1: Database Setup

The migration is deployed automatically by the deployment script. If deploying manually via SSH to the production host:

```bash
# SSH to production (65.1.42.221)
ssh root@65.1.42.221

# Navigate to gate directory
cd /opt/gate

# Run migration via Docker Compose (database runs in Docker container)
docker compose -f deploy/app/compose.yaml exec -T gate-postgres psql -U gate -d gate << 'EOF'
$(cat db/018_langsmith_integration.sql)
EOF
```

This creates:
- `langsmith_traces` table - stores trace data
- `dash_traces` view - correlates LangSmith + gateway data
- `dash_langsmith_costs` view - cost aggregation
- Permissions for `gate_readonly` role

## Step 2: Environment Configuration

Add LangSmith API key to your gateway environment:

```bash
# In /etc/gate/env or similar
LANGSMITH_API_KEY=ls_your_api_key_here

# Optional: customize sync interval (default every 5 min)
LANGSMITH_SYNC_INTERVAL=5
```

## Step 3: Install Sync Service

Copy systemd files to your system:

```bash
sudo cp deploy/systemd/gate-langsmith-sync.{service,timer} /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable gate-langsmith-sync.timer
sudo systemctl start gate-langsmith-sync.timer

# Verify it's running
sudo systemctl status gate-langsmith-sync.timer
sudo systemctl list-timers gate-langsmith*

# Watch logs
journalctl -u gate-langsmith-sync -f
```

The service runs every 5 minutes and fetches the last 10 minutes of traces from LangSmith.

## Step 4: Configure Grafana

### Add Dashboard

The dashboard is automatically provisioned if you have Grafana watching the `grafana/dashboards/` directory:

```bash
# In your Grafana provisioning config
provision:
  dashboardproviders:
    dashboardproviders.yaml:
      - name: 'default'
        org_id: 1
        folder: ''
        type: 'file'
        options:
          path: /etc/grafana/provisioning/dashboards
```

Or manually import `grafana/dashboards/gate-langsmith.json` into Grafana.

### Configure Postgres Datasource

Ensure your Grafana Postgres datasource:
- Connects to the same database as gate.atla.in
- Uses read-only role: `gate_readonly`
- Has database: `gate`

Test the connection:
```sql
SELECT COUNT(*) FROM langsmith_traces LIMIT 1;
```

### Add to Dashboard Overview

Edit your Grafana homepage to add a link to the LangSmith dashboard:

```json
{
  "title": "gate.atla.in · LangSmith Traces",
  "url": "/d/gate-langsmith",
  "tags": ["gate", "observability"]
}
```

## Step 5: Configure Alerts (Optional)

Import alert rules from `deploy/grafana/alerts/langsmith-alerts.yaml`:

1. Go to Grafana → Alerting → Alert Rules → New Alert Rule
2. Configure each rule:
   - **High Latency**: Alert if avg latency > 5s
   - **High Error Rate**: Alert if error rate > 10%
   - **Mismatch**: Warn if trace has no gateway record

3. Set notification channel to include LangSmith trace links:
   ```
   View trace: https://smith.langchain.com/runs/{{ .Alerts.Firing.0.Labels.ls_run_id }}
   ```

## Usage

### Viewing Traces

1. **Dashboard**: Open Grafana → `gate.atla.in · LangSmith Traces`
2. **Recent Traces Table**: Shows last 1 hour of traces with links
3. **Click "View in LangSmith"**: Opens full trace in LangSmith UI

### Finding Specific Requests

By request_id (from gateway audit log):

```sql
SELECT * FROM dash_traces WHERE request_id = 'abc-123-def-456';
```

By question text (now recorded in LangSmith):

```sql
SELECT * FROM langsmith_traces 
WHERE created_at > now() - interval '1h'
  AND input_data::text ILIKE '%your question%';
```

By cost:

```sql
SELECT * FROM langsmith_traces 
WHERE created_at > now() - interval '24h'
  AND cost_usd > 0.01
ORDER BY cost_usd DESC;
```

## Troubleshooting

### Traces Not Appearing

1. Check sync service is running:
   ```bash
   sudo systemctl status gate-langsmith-sync.timer
   sudo journalctl -u gate-langsmith-sync -n 20
   ```

2. Verify LangSmith API key:
   ```bash
   curl -H "x-api-key: $LANGSMITH_API_KEY" \
     https://api.smith.langchain.com/runs?limit=1
   ```

3. Check Postgres table:
   ```sql
   SELECT COUNT(*) FROM langsmith_traces;
   SELECT MAX(created_at) FROM langsmith_traces;
   ```

### Grafana Dashboard Empty

1. Verify Postgres datasource is connected
2. Test query manually:
   ```sql
   SELECT created_at, run_name, status FROM langsmith_traces LIMIT 5;
   ```
3. Check that traces exist in the date range selected on dashboard

### Missing Input/Output Data

Make sure you've deployed the updated `app/tracing.py` with serialization functions. Without it, inputs/outputs will show as empty.

## Data Retention

By default, traces are kept for 30 days (can be adjusted):

```sql
-- Manual cleanup of old traces
DELETE FROM langsmith_traces 
WHERE created_at < now() - interval '30 days';
```

## Cost

LangSmith trace storage costs:
- First 1M traces/month: free
- Each additional 1M traces: ~$1.50/month at typical volumes
- This gateway example: ~$0.10/month (1-5 traces per minute)

---

**Next**: Check the dashboard is working, then explore correlations between gateway metrics and LangSmith traces.
