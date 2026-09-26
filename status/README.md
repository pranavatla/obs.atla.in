# Status snapshot

`collect_status.py` gathers real metrics for every atla.in site and writes `status.json`, which
obs.atla.in renders. `.github/workflows/publish-status.yml` runs it every 15 minutes and uploads
the file to the obs.atla.in bucket. The site list is `DOMAINS` in `grafana/build_dashboards.py`,
shared with the Grafana dashboards.

Why a snapshot instead of an embedded dashboard: CloudWatch bills per metric fetched, so cost
stays fixed at one collection per 15 minutes however many people (or bots) load the page, and
Grafana and AWS stay private.

## `status.json` (schema_version 1)

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-09-26T12:00:00Z",       // end of both windows
  "windows": {"24h": {"start": "…", "end": "…"}, "7d": {"start": "…", "end": "…"}},
  "signal_type": "measured",
  "sites": [
    {
      "domain": "atla.in",
      "name": "Portfolio",
      "description": "…",
      "status": "up",                            // up | down | unknown (no check data)
      "metrics": [
        {"key": "uptime_7d", "label": "Uptime", "value": 100.0, "unit": "percent",
         "window": "7d", "source": "Grafana Synthetic Monitoring check …", "note": "…"}
      ],
      "series": {"requests_hourly_24h": [0, 3, …]}   // 24 values, oldest first
    }
  ],
  "ai_models": [                                // every Bedrock model with activity, discovered
    {"model_id": "global.amazon.nova-2-lite-v1:0", "region": "ap-south-1", "role": "Text generation",
     "used_by": ["gita.atla.in"], "calls_7d": 3483, "input_tokens_7d": 3240000, "output_tokens_7d": 518000,
     "latency_p90_ms_7d": 1600, "cost_usd_7d": 2.66, "cost_note": "…", "source": "…"}
  ],
  "unavailable_sources": ["gita.atla.in Bedrock: …"]  // what failed this run, and why
}
```

`value` is `null` when a source returned no data. A source that fails is listed in
`unavailable_sources` and its metrics are left out rather than guessed.

Units: `percent` (0–100), `ms`, `count`, `bytes`, `usd`, `score` (CLS).

| Key | Sites | Meaning |
|---|---|---|
| `uptime_24h`, `uptime_7d`, `check_duration_24h` | all | Uptime check results |
| `requests_24h`, `requests_7d` | all | Requests, bots included |
| `error_5xx_rate_7d` | all | Request-weighted 5xx rate |
| `error_4xx_rate_7d` | all | Request-weighted 4xx rate (includes firewall blocks where a WAF exists) |
| `bytes_7d` | CloudFront sites | Data served |
| `error_5xx_count_7d`, `response_p90_24h` | gita | Load balancer 5xx count, app response time |
| `waf_blocked_7d`, `waf_blocked_share_7d` | atla.in, games, obs, gita | AWS WAF blocks (aif has no WAF) |
| `page_views_7d`, `lcp_p75_7d`, `cls_p75_7d`, `inp_p75_7d`, `js_errors_7d` | all | Real visitors (RUM), one app monitor per site |
| `llm_calls_7d`, `llm_tokens_7d`, `llm_latency_p90_7d`, `bedrock_cost_7d` | gita | Amazon Bedrock |

## Bedrock models

`ai_models` lists every model with Bedrock activity in the last 7 days in `BEDROCK_REGIONS`, found
with `cloudwatch:ListMetrics` rather than assumed, so a newly used model (a Claude model, for
example) appears without code changes. `used_by` and prices come from the site list; a model not in
it shows `used_by: []` and `cost_usd_7d: null` rather than a guessed site or price.

## Run locally

```bash
export GRAFANA_PROM_URL=… GRAFANA_PROM_USER=… GRAFANA_PROM_TOKEN=…   # optional
AWS_PROFILE=atla-admin python3 status/collect_status.py --out /tmp/status.json
python3 -m unittest tests/test_collect_status.py
```
