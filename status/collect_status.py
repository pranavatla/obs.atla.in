"""Collect a public status snapshot for every atla.in site and write it as JSON.

Run by .github/workflows/publish-status.yml every 15 minutes; obs.atla.in renders the result.
Sources are the same ones the Grafana dashboards read:

  - Uptime checks: Grafana Cloud Prometheus (Synthetic Monitoring), over its HTTP API
  - CloudFront, WAF, RUM: CloudWatch in us-east-1
  - Load balancer, Bedrock: CloudWatch in the site's region

Every metric carries its source and window. A source that fails is recorded as unavailable with
the reason, never replaced by a guessed value.

Environment:
  GRAFANA_PROM_URL    e.g. https://prometheus-prod-43-prod-ap-south-1.grafana.net/api/prom
  GRAFANA_PROM_USER   the Prometheus instance ID (a number)
  GRAFANA_PROM_TOKEN  a Grafana Cloud access policy token with the metrics:read scope

Usage: python3 status/collect_status.py --out site/status.json
"""

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grafana"))
from build_dashboards import DOMAINS  # noqa: E402  (one site list for dashboards and status)

SCHEMA_VERSION = 1
DAY, WEEK = timedelta(days=1), timedelta(days=7)


def iso(t):
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ── Sources ──────────────────────────────────────────────────────────────────

class Prometheus:
    def __init__(self, url, user, token):
        self.url = url.rstrip("/")
        self.auth = "Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()

    def query(self, promql):
        """Instant query; returns {job: float}."""
        req = urllib.request.Request(
            f"{self.url}/api/v1/query?" + urllib.parse.urlencode({"query": promql}),
            headers={"Authorization": self.auth})
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
        if body.get("status") != "success":
            raise RuntimeError(body.get("error", "query failed"))
        return {r["metric"].get("job", ""): float(r["value"][1]) for r in body["data"]["result"]}


class CloudWatch:
    """GetMetricData over one window; returns {id: [(timestamp, value), ...]} oldest first."""

    def __init__(self, region):
        import boto3
        self.client = boto3.client("cloudwatch", region_name=region)

    def fetch(self, queries, start, end):
        out = {q["Id"]: [] for q in queries}
        for page in self.client.get_paginator("get_metric_data").paginate(
                MetricDataQueries=queries, StartTime=start, EndTime=end, ScanBy="TimestampAscending"):
            for r in page["MetricDataResults"]:
                out[r["Id"]].extend(zip(r["Timestamps"], r["Values"]))
        return out


def stat_query(qid, namespace, metric, dims, stat, period):
    return {"Id": qid, "ReturnData": True, "MetricStat": {
        "Metric": {"Namespace": namespace, "MetricName": metric,
                   "Dimensions": [{"Name": k, "Value": v} for k, v in dims.items()]},
        "Period": period, "Stat": stat}}


# ── Metric records ───────────────────────────────────────────────────────────

def metric(key, label, value, unit, window, source, note=None):
    rec = {"key": key, "label": label, "value": value, "unit": unit, "window": window, "source": source}
    if note:
        rec["note"] = note
    return rec


def scaled(value, factor):
    return None if value is None else value * factor


def total(points):
    return sum(v for _, v in points) if points else None


def weighted_rate(requests, rates):
    """Request-weighted error rate (%) from per-minute request counts and error-rate percentages."""
    rate_at = dict(rates)
    reqs = sum(v for _, v in requests)
    errors = sum(v * rate_at.get(t, 0) / 100 for t, v in requests)
    return (errors / reqs * 100) if reqs else None


def hourly(points, end, hours=24):
    """Hourly buckets for the last `hours` hours, oldest first; hours with no data are 0."""
    start = end - timedelta(hours=hours)
    buckets = [0.0] * hours
    for t, v in points:
        i = int((t - start).total_seconds() // 3600)
        if 0 <= i < hours:
            buckets[i] += v
    return buckets


# ── Collectors ───────────────────────────────────────────────────────────────

def availability(prom, sites, errors):
    """Status, uptime and check duration for every site, in four Prometheus queries."""
    out = {s["sm_job"]: {} for s in sites}
    if prom is None:
        errors.append("uptime checks: Prometheus credentials not configured")
        return out
    jobs = "|".join(s["sm_job"].replace(".", "\\\\.") for s in sites)
    sel = f'job=~"{jobs}"'
    queries = {
        "up_now": f"min by (job) (probe_success{{{sel}}})",
        "uptime_24h": f"avg by (job) (avg_over_time(probe_success{{{sel}}}[24h]))",
        "uptime_7d": f"avg by (job) (avg_over_time(probe_success{{{sel}}}[7d]))",
        "duration_24h": f"avg by (job) (avg_over_time(probe_duration_seconds{{{sel}}}[24h]))",
    }
    for name, promql in queries.items():
        try:
            for job, value in prom.query(promql).items():
                if job in out:
                    out[job][name] = value
        except Exception as exc:  # recorded, not fatal: other sources still publish
            errors.append(f"uptime checks ({name}): {exc}")
    return out


def cloudfront_metrics(cw, dist, end, src):
    minute = cw.fetch([
        stat_query("req", "AWS/CloudFront", "Requests", {"DistributionId": dist, "Region": "Global"}, "Sum", 60),
        stat_query("e5", "AWS/CloudFront", "5xxErrorRate", {"DistributionId": dist, "Region": "Global"}, "Average", 60),
        stat_query("e4", "AWS/CloudFront", "4xxErrorRate", {"DistributionId": dist, "Region": "Global"}, "Average", 60),
        stat_query("bytes", "AWS/CloudFront", "BytesDownloaded", {"DistributionId": dist, "Region": "Global"}, "Sum", 3600),
    ], end - WEEK, end)
    last_day = [(t, v) for t, v in minute["req"] if t >= end - DAY]
    return [
        metric("requests_7d", "Requests", total(minute["req"]) or 0, "count", "7d", src,
               "Every file fetched, bots included; not visitors."),
        metric("requests_24h", "Requests", total(last_day) or 0, "count", "24h", src),
        metric("error_5xx_rate_7d", "5xx rate", weighted_rate(minute["req"], minute["e5"]), "percent", "7d", src,
               "Request-weighted."),
        metric("error_4xx_rate_7d", "4xx rate", weighted_rate(minute["req"], minute["e4"]), "percent", "7d", src,
               "Request-weighted; includes firewall blocks and bots requesting missing paths."),
        metric("bytes_7d", "Data served", total(minute["bytes"]) or 0, "bytes", "7d", src),
    ], {"requests_hourly_24h": hourly(minute["req"], end)}


def waf_metrics(cw, acl, end):
    src = f"CloudWatch AWS/WAFV2 us-east-1, web ACL {acl}"
    r = cw.fetch([stat_query(q, "AWS/WAFV2", m, {"WebACL": acl, "Rule": "ALL"}, "Sum", 3600)
                  for q, m in (("blocked", "BlockedRequests"), ("allowed", "AllowedRequests"))], end - WEEK, end)
    blocked, allowed = total(r["blocked"]) or 0, total(r["allowed"]) or 0
    return [
        metric("waf_blocked_7d", "Blocked by firewall", blocked, "count", "7d", src),
        metric("waf_blocked_share_7d", "Share blocked",
               blocked / (blocked + allowed) * 100 if blocked + allowed else None, "percent", "7d", src),
    ]


def rum_metrics(cw, app, end):
    src = f"CloudWatch AWS/RUM us-east-1, app monitor {app}"
    dims = {"application_name": app}
    week = int(WEEK.total_seconds())
    r = cw.fetch([
        stat_query("views", "AWS/RUM", "PageViewCount", dims, "Sum", week),
        stat_query("lcp", "AWS/RUM", "WebVitalsLargestContentfulPaint", dims, "p75", week),
        stat_query("cls", "AWS/RUM", "WebVitalsCumulativeLayoutShift", dims, "p75", week),
        stat_query("inp", "AWS/RUM", "WebVitalsInteractionToNextPaint", dims, "p75", week),
        stat_query("jserr", "AWS/RUM", "JsErrorCount", dims, "Sum", week),
    ], end - WEEK, end)
    last = lambda k: r[k][-1][1] if r[k] else None  # noqa: E731
    return [
        metric("page_views_7d", "Page views", total(r["views"]) or 0, "count", "7d", src, "Real browsers only."),
        metric("lcp_p75_7d", "LCP (p75)", last("lcp"), "ms", "7d", src, "Good ≤ 2500 ms."),
        metric("cls_p75_7d", "CLS (p75)", last("cls"), "score", "7d", src, "Good ≤ 0.1."),
        metric("inp_p75_7d", "INP (p75)", last("inp"), "ms", "7d", src, "Good ≤ 200 ms."),
        metric("js_errors_7d", "JavaScript errors", total(r["jserr"]) or 0, "count", "7d", src),
    ]


def alb_metrics(cw, lb, region, end):
    src = f"CloudWatch AWS/ApplicationELB {region}, load balancer {lb}"
    dims = {"LoadBalancer": lb}
    r = cw.fetch([
        stat_query("req", "AWS/ApplicationELB", "RequestCount", dims, "Sum", 300),
        stat_query("t5", "AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", dims, "Sum", 300),
        stat_query("l5", "AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", dims, "Sum", 300),
        stat_query("rt", "AWS/ApplicationELB", "TargetResponseTime", dims, "p90", int(DAY.total_seconds())),
    ], end - WEEK, end)
    reqs = total(r["req"]) or 0
    err5 = (total(r["t5"]) or 0) + (total(r["l5"]) or 0)
    last_day = [(t, v) for t, v in r["req"] if t >= end - DAY]
    return [
        metric("requests_7d", "Requests", reqs, "count", "7d", src, "Bots included; not visitors."),
        metric("requests_24h", "Requests", total(last_day) or 0, "count", "24h", src),
        metric("error_5xx_count_7d", "5xx responses", err5, "count", "7d", src, "App and load balancer."),
        metric("error_5xx_rate_7d", "5xx rate", err5 / reqs * 100 if reqs else None, "percent", "7d", src),
        metric("response_p90_24h", "Response time (p90)", r["rt"][-1][1] * 1000 if r["rt"] else None,
               "ms", "24h", src),
    ], {"requests_hourly_24h": hourly(r["req"], end)}


def bedrock_metrics(cw, cfg, end):
    b = cfg["bedrock"]
    src = f"CloudWatch AWS/Bedrock {b['region']}"
    r = cw.fetch([
        stat_query("calls", "AWS/Bedrock", "Invocations", {"ModelId": b["llm"]}, "Sum", 3600),
        stat_query("tin", "AWS/Bedrock", "InputTokenCount", {"ModelId": b["llm"]}, "Sum", 3600),
        stat_query("tout", "AWS/Bedrock", "OutputTokenCount", {"ModelId": b["llm"]}, "Sum", 3600),
        stat_query("ein", "AWS/Bedrock", "InputTokenCount", {"ModelId": b["embed"]}, "Sum", 3600),
        stat_query("lat", "AWS/Bedrock", "InvocationLatency", {"ModelId": b["llm"]}, "p90", int(WEEK.total_seconds())),
    ], end - WEEK, end)
    p = {k: float(v) for k, v in b["prices"].items()}
    tin, tout, ein = total(r["tin"]) or 0, total(r["tout"]) or 0, total(r["ein"]) or 0
    cost = tin / 1000 * p["llm_in"] + tout / 1000 * p["llm_out"] + ein / 1000 * p["embed_in"]
    return [
        metric("llm_calls_7d", "LLM calls", total(r["calls"]) or 0, "count", "7d", src, b["llm"]),
        metric("llm_tokens_7d", "LLM tokens", tin + tout, "count", "7d", src, "Input and output."),
        metric("llm_latency_p90_7d", "LLM latency (p90)", r["lat"][-1][1] if r["lat"] else None, "ms", "7d", src),
        metric("bedrock_cost_7d", "Bedrock cost (est.)", round(cost, 4), "usd", "7d", src,
               "Tokens × on-demand prices from the AWS Price List; check AWS Billing for the charge."),
    ]


# ── Snapshot ─────────────────────────────────────────────────────────────────

def site_record(cfg, avail, cw_clients, end, errors):
    a = avail.get(cfg["sm_job"], {})
    sm_src = f"Grafana Synthetic Monitoring check \"{cfg['sm_job']}\", {cfg['sm_schedule']}"
    up = a.get("up_now")
    rec = {
        "domain": cfg["domain"],
        "name": cfg["notes"].split(":")[0],
        "description": cfg["notes"],
        "status": "up" if up == 1 else "down" if up == 0 else "unknown",
        "metrics": [
            metric("uptime_24h", "Uptime", scaled(a.get("uptime_24h"), 100), "percent", "24h", sm_src),
            metric("uptime_7d", "Uptime", scaled(a.get("uptime_7d"), 100), "percent", "7d", sm_src),
            metric("check_duration_24h", "Check duration", scaled(a.get("duration_24h"), 1000),
                   "ms", "24h", sm_src, "DNS, connect, TLS and response, from outside."),
        ],
        "series": {},
    }

    def add(name, fn):
        try:
            result = fn()
            mets, series = result if isinstance(result, tuple) else (result, {})
            rec["metrics"] += mets
            rec["series"].update(series)
        except Exception as exc:
            errors.append(f"{cfg['domain']} {name}: {exc}")

    if "distribution" in cfg:
        src = f"CloudWatch AWS/CloudFront us-east-1, distribution {cfg['distribution']}"
        add("CloudFront", lambda: cloudfront_metrics(cw_clients("us-east-1"), cfg["distribution"], end, src))
    if "waf_acl" in cfg:
        add("WAF", lambda: waf_metrics(cw_clients("us-east-1"), cfg["waf_acl"], end))
    if "rum_app" in cfg:
        add("RUM", lambda: rum_metrics(cw_clients("us-east-1"), cfg["rum_app"], end))
    if "alb" in cfg:
        add("load balancer", lambda: alb_metrics(cw_clients(cfg["region"]), cfg["alb"], cfg["region"], end))
    if "bedrock" in cfg:
        add("Bedrock", lambda: bedrock_metrics(cw_clients(cfg["bedrock"]["region"]), cfg, end))
    return rec


def snapshot(prom, cw_clients, now=None, sites=DOMAINS):
    end = (now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    errors = []
    avail = availability(prom, sites, errors)
    records = [site_record(cfg, avail, cw_clients, end, errors) for cfg in sites]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso(end),
        "windows": {"24h": {"start": iso(end - DAY), "end": iso(end)},
                    "7d": {"start": iso(end - WEEK), "end": iso(end)}},
        "signal_type": "measured",
        "sites": records,
        "unavailable_sources": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    prom = None
    if all(os.environ.get(k) for k in ("GRAFANA_PROM_URL", "GRAFANA_PROM_USER", "GRAFANA_PROM_TOKEN")):
        prom = Prometheus(os.environ["GRAFANA_PROM_URL"], os.environ["GRAFANA_PROM_USER"],
                          os.environ["GRAFANA_PROM_TOKEN"])
    clients = {}

    def cw_clients(region):
        if region not in clients:
            clients[region] = CloudWatch(region)
        return clients[region]

    data = snapshot(prom, cw_clients)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {args.out}: {len(data['sites'])} sites, {len(data['unavailable_sources'])} unavailable sources")
    for e in data["unavailable_sources"]:
        print(f"  unavailable: {e}")


if __name__ == "__main__":
    main()
