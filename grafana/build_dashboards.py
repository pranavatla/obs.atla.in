"""Generate the Grafana dashboards in grafana/dashboards/ from one definition per domain.

Run:  python3 grafana/build_dashboards.py

Each domain dashboard includes only the sections its setup supports (for example, no
Security section without a WAF web ACL). The overview dashboard shows one line per domain.
Every panel description names its data source, so a reader can tell measured data from gaps.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dashboards"

DOMAINS = [
    {
        "slug": "atla-in", "uid": "atla-in-delivery", "domain": "atla.in",
        "distribution": "E2OMRFTQ27WGMZ", "sm_job": "atla.in homepage", "sm_schedule": "every 5 minutes from 3 probes",
        "waf_acl": "CreatedByCloudFront-14eef7b4", "rum_app": "atla-in",
        "deploy_tags": ["atla.in", "deploy"],
        "notes": "Portfolio: Next.js static export in S3 behind CloudFront (Free plan, AWS WAF included).",
    },
    {
        "slug": "aif-atla-in", "uid": "aif-atla-in", "domain": "aif.atla.in",
        "distribution": "E2A5DBVVXUZ6JO", "sm_job": "aif.atla.in homepage", "rum_app": "aif-atla-in", "sm_schedule": "every 10 minutes from 2 probes",
        "notes": "AIF-C01 study site: S3 website endpoint (us-east-1) behind CloudFront (pay-as-you-go). No WAF.",
    },
    {
        "slug": "games-atla-in", "uid": "games-atla-in", "domain": "games.atla.in",
        "distribution": "E1HCLV5K7MXCST", "sm_job": "games.atla.in homepage", "waf_acl": "CreatedByCloudFront-af869b7f", "rum_app": "games-atla-in", "sm_schedule": "every 10 minutes from 2 probes",
        "notes": "Games site: S3 website endpoint (ap-south-1) behind CloudFront (Free plan, AWS WAF included).",
    },
    {
        "slug": "obs-atla-in", "uid": "obs-atla-in", "domain": "obs.atla.in",
        "distribution": "E2EXL4C10F3QBA", "sm_job": "obs.atla.in homepage", "waf_acl": "CreatedByCloudFront-44b6e91d", "rum_app": "obs-atla-in", "sm_schedule": "every 10 minutes from 2 probes",
        "notes": "Observability page: private S3 bucket behind CloudFront (Free plan, AWS WAF included).",
    },
    {
        "slug": "gita-atla-in", "uid": "gita-atla-in", "domain": "gita.atla.in",
        "sm_job": "gita.atla.in homepage", "rum_app": "gita-atla-in", "sm_schedule": "every 5 minutes from 3 probes",
        "alb": "app/k8s-gita-gitaapp-62bac50d1f/3f31a5493e811f77", "region": "ap-south-1",
        "waf_acl": "gita-atla-in", "waf_region": "ap-south-1",
        "bedrock": {"region": "ap-south-1", "llm": "global.amazon.nova-2-lite-v1:0",
                    "embed": "amazon.titan-embed-text-v2:0",
                    # USD per 1K tokens, on-demand, from the AWS Price List for ap-south-1
                    # (published 2026-09-26): Nova 2.0 Lite cross-region global, Titan Embeddings V2.
                    "prices": {"llm_in": "0.00035", "llm_out": "0.00295", "embed_in": "0.000024"}},
        "notes": "Gita RAG app: FastAPI on EKS (gita-rag-cluster) behind an Application Load Balancer, "
                 "answering with Amazon Bedrock. Regional AWS WAF on the load balancer; no CloudFront.",
    },
]

CW = {"type": "cloudwatch", "uid": "${datasource}"}
PROM = {"type": "prometheus", "uid": "${prom}"}
EXPR = {"type": "__expr__", "uid": "__expr__"}

CF_SRC = " Measured · CloudWatch AWS/CloudFront (us-east-1) · distribution ${distribution}."
SM_SRC = " Measured · Grafana Synthetic Monitoring check \"${sm_job}\"."
WAF_SRC = " Measured · CloudWatch AWS/WAFV2 (${waf_region}) · web ACL ${waf_acl}."
RUM_SRC = (" Measured · CloudWatch AWS/RUM (us-east-1) · app monitor ${rum_app}. "
           "Browsers of real visitors only; most bots do not run JavaScript.")
ALB_SRC = " Measured · CloudWatch AWS/ApplicationELB (${region}) · load balancer ${alb}."
BR_SRC = " Measured · CloudWatch AWS/Bedrock (${bedrock_region}) · calls made by the app."
WEIGHTED = (" Weighted by requests: per minute, errors = rate × requests; the panel shows total errors ÷ "
            "total requests, so quiet minutes with a single failed request don't dominate.")

NEUTRAL = [{"color": "text", "value": None}]


def steps(*pairs):
    """Threshold steps from (color, from_value) pairs; the first applies from -infinity."""
    return [{"color": c, "value": v} for c, v in pairs]


def good_poor(good_max, poor_min):
    return steps(("green", None), ("yellow", good_max), ("red", poor_min))


ZERO_IS_GOOD = steps(("green", None), ("red", 1))


# ── Queries ──────────────────────────────────────────────────────────────────

def cw_metric(ref, namespace, metric, stat, dims, period="", label=None, hide=False):
    return {"datasource": CW, "refId": ref, "hide": hide, "queryMode": "Metrics",
            "metricQueryType": 0, "metricEditorMode": 0, "region": "us-east-1",
            "namespace": namespace, "metricName": metric, "statistic": stat,
            "dimensions": dims, "matchExact": True, "period": period,
            "id": "", "expression": "", "label": label or metric}


def cf(ref, metric, stat, period="", label=None, hide=False, dist="${distribution}"):
    return cw_metric(ref, "AWS/CloudFront", metric, stat,
                     {"DistributionId": dist, "Region": "Global"}, period, label, hide)


def waf(ref, metric, label, hide=False, regional=False):
    # CloudFront web ACLs report in us-east-1 by WebACL and Rule; regional ones (an ALB's) also
    # carry a Region dimension and report in their own region.
    dims = {"WebACL": "${waf_acl}", "Rule": "ALL", **({"Region": "${waf_region}"} if regional else {})}
    return {**cw_metric(ref, "AWS/WAFV2", metric, "Sum", dims, "3600", label, hide), "region": "${waf_region}"}


def waf_search(schema, metric, label_dim, regional=False):
    if regional:
        schema = "Region," + schema
    expr = (f"SEARCH('{{AWS/WAFV2,{schema}}} MetricName=\"{metric}\" WebACL=\"${{waf_acl}}\"', "
            "'Sum', 3600)")
    return {"datasource": CW, "refId": "A", "queryMode": "Metrics", "metricQueryType": 0,
            "metricEditorMode": 1, "region": "${waf_region}", "expression": expr, "id": "",
            "period": "3600", "label": "${PROP('Dim." + label_dim + "')}"}


def cw_search(ref, region, expression, label, hide=False, query_id=""):
    """A CloudWatch search or metric-math expression, for metrics whose full dimension
    values are generated (the load balancer's ARN suffix) or span several models."""
    return {"datasource": CW, "refId": ref, "hide": hide, "queryMode": "Metrics",
            "metricQueryType": 0, "metricEditorMode": 1, "region": region,
            "expression": expression, "id": query_id, "period": "300", "label": label}


def alb(ref, metric, stat, label, hide=False, name="${alb}", region="${region}", period="300"):
    """A load balancer metric; name is the LoadBalancer dimension, app/<name>/<id>."""
    return {**cw_metric(ref, "AWS/ApplicationELB", metric, stat, {"LoadBalancer": name}, period, label, hide),
            "region": region}


def alb_5xx_total(ref, name, region, period=300):
    """App and load balancer 5xx together. The load balancer publishes each count only when such
    errors happen, so a search over both names returns whichever exist."""
    expr = ("SUM(SEARCH('{AWS/ApplicationELB,LoadBalancer} LoadBalancer=\"" + name + "\" "
            "(MetricName=\"HTTPCode_Target_5XX_Count\" OR MetricName=\"HTTPCode_ELB_5XX_Count\")', "
            f"'Sum', {period}))")
    return cw_search(ref, region, expr, "5xx")


def bedrock_search(ref, metrics, stat, label, model=None, period=3600):
    """Bedrock metrics across models (or one model), summed into one series."""
    names = " OR ".join(f"MetricName=\"{m}\"" for m in metrics)
    model_filter = f" ModelId=\"{model}\"" if model else ""
    expr = f"FILL(SUM(SEARCH('{{AWS/Bedrock,ModelId}} ({names}){model_filter}', '{stat}', {period})), 0)"
    return cw_search(ref, "${bedrock_region}", expr, label)


def bedrock(ref, metric, stat, model, label, hide=False, query_id=""):
    return {**cw_metric(ref, "AWS/Bedrock", metric, stat, {"ModelId": model}, "3600", label, hide),
            "region": "${bedrock_region}", "id": query_id}


def rum(ref, metric, stat, period="3600", label=None):
    return cw_metric(ref, "AWS/RUM", metric, stat, {"application_name": "${rum_app}"},
                     period, label)


def prom(expr, legend, instant=True):
    return {"datasource": PROM, "refId": "A", "expr": expr, "instant": instant,
            "range": not instant, "legendFormat": legend}


def math(ref, expression, hide=True):
    return {"datasource": EXPR, "refId": ref, "type": "math", "expression": expression, "hide": hide}


def reduce_sum(ref, source):
    return {"datasource": EXPR, "refId": ref, "type": "reduce", "expression": source,
            "reducer": "sum", "hide": True}


def resample_sum(ref, source):
    return {"datasource": EXPR, "refId": ref, "type": "resample", "expression": source,
            "window": "1h", "downsampler": "sum", "upsampler": "fillna", "hide": True}


def weighted_rate(metric, dist="${distribution}"):
    """Request-weighted error rate over the whole range, as one number."""
    return [cf("A", "Requests", "Sum", "60", hide=True, dist=dist),
            cf("B", metric, "Average", "60", hide=True, dist=dist),
            math("C", "$A * $B / 100"), reduce_sum("D", "C"), reduce_sum("E", "A"),
            math("F", "$D / $E * 100", hide=False)]


# ── Panels ───────────────────────────────────────────────────────────────────

class Layout:
    """Hands out panel ids and stacks panels top to bottom on Grafana's 24-column grid."""

    def __init__(self):
        self.y, self.next_id, self.panels = 0, 1, []

    def add(self, panel, x, w, h, advance=False):
        panel["id"] = self.next_id
        self.next_id += 1
        panel["gridPos"] = {"h": h, "w": w, "x": x, "y": self.y}
        self.panels.append(panel)
        if advance:
            self.y += h

    def row(self, title):
        self.add({"type": "row", "title": title, "collapsed": False, "panels": []}, 0, 24, 1, True)

    def line(self, panels, h):
        """Places panels side by side, widths given per panel, then moves below them."""
        x = 0
        for panel, w in panels:
            self.add(panel, x, w, h)
            x += w
        self.y += h


def stat(title, desc, targets, unit, thresholds=NEUTRAL, calc="lastNotNull", decimals=None,
         mappings=None, sparkline=False, no_value=None, datasource=CW):
    defaults = {"unit": unit, "displayName": title, "color": {"mode": "thresholds"},
                "thresholds": {"mode": "absolute", "steps": thresholds}}
    if decimals is not None:
        defaults["decimals"] = decimals
    if mappings:
        defaults["mappings"] = mappings
    if no_value:
        defaults["noValue"] = no_value
    return {"type": "stat", "title": title, "description": desc, "datasource": datasource,
            "targets": targets, "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"reduceOptions": {"calcs": [calc], "fields": "", "values": False},
                        "colorMode": "value", "graphMode": "area" if sparkline else "none",
                        "textMode": "value", "justifyMode": "auto", "orientation": "auto"}}


def series(title, desc, targets, unit, draw="line", stacked=False, overrides=None, no_value=None):
    custom = {"drawStyle": draw, "lineWidth": 2 if draw == "line" else 1,
              "fillOpacity": 10 if draw == "line" else 60, "spanNulls": draw == "line",
              "showPoints": "never" if draw == "bars" else "auto"}
    if stacked:
        custom["stacking"] = {"mode": "normal"}
    defaults = {"unit": unit, "min": 0, "custom": custom}
    if no_value:
        defaults["noValue"] = no_value
    return {"type": "timeseries", "title": title, "description": desc, "datasource": CW,
            "targets": targets, "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "none"}}}


def top_table(title, desc, target, header):
    return {"type": "table", "title": title, "description": desc, "datasource": CW,
            "targets": [target],
            "transformations": [
                {"id": "reduce", "options": {"mode": "seriesToRows", "reducers": ["sum"]}},
                {"id": "sortBy", "options": {"sort": [{"field": "Total", "desc": True}]}},
                {"id": "limit", "options": {"limitField": 10}},
                {"id": "organize", "options": {"renameByName": {"Field": header, "Total": "Requests"}}}],
            "fieldConfig": {"defaults": {"unit": "short", "decimals": 0}, "overrides": [
                {"matcher": {"id": "byName", "options": "Requests"},
                 "properties": [{"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic"}}]}]},
            "options": {"showHeader": True, "cellHeight": "sm"}}


def text(title, content):
    return {"type": "text", "title": title, "options": {"mode": "markdown", "content": content}}


def status_now(sel, title="Status now"):
    return stat(title, "Whether the latest run of the uptime check succeeded from every probe." + SM_SRC,
                [prom(f"min(probe_success{{{sel}}})", title)], "none",
                steps(("red", None), ("green", 1)), datasource=PROM,
                mappings=[{"type": "value", "options": {"0": {"text": "DOWN", "color": "red"},
                                                         "1": {"text": "UP", "color": "green"}}}],
                no_value="No check")


def uptime(sel, title="Uptime"):
    # probe_success is 1 or 0 per probe per run, so its average over the range is the success
    # share; unlike counter increases it needs no minimum number of runs.
    return stat(title, "Share of check runs that succeeded over the selected range, across all probes." + SM_SRC,
                [prom(f"avg(avg_over_time(probe_success{{{sel}}}[$__range]))", title)],
                "percentunit", steps(("red", None), ("yellow", 0.99), ("green", 0.999)),
                decimals=2, datasource=PROM, no_value="No check")


def check_duration(sel, title="Check duration"):
    return stat(title, "Average time for one check run (DNS, connect, TLS, response) over the selected range." + SM_SRC,
                [prom(f"avg(avg_over_time(probe_duration_seconds{{{sel}}}[$__range]))", title)],
                "s", good_poor(2, 5), decimals=2, datasource=PROM, no_value="No check")


# ── Sections ─────────────────────────────────────────────────────────────────

def availability(lay):
    sel = 'job="${sm_job}"'
    lay.row("Availability")
    failed = stat("Failed check runs", "Check runs that failed over the selected range, across all probes." + SM_SRC,
                  [prom(f"sum(increase(probe_all_success_count{{{sel}}}[$__range])) - "
                        f"sum(increase(probe_all_success_sum{{{sel}}}[$__range]))", "Failed")],
                  "short", ZERO_IS_GOOD, decimals=0, datasource=PROM, no_value="No check")
    lay.line([(status_now(sel), 6), (uptime(sel), 6), (check_duration(sel), 6), (failed, 6)], 4)


def real_visitors(lay):
    lay.row("Real visitors · CloudWatch RUM")
    nv = "No visits yet"
    lay.line([
        (stat("Page views", "Page loads recorded by the RUM script in visitors' browsers." + RUM_SRC,
              [rum("A", "PageViewCount", "Sum")], "short", calc="sum", decimals=0, no_value=nv), 4),
        (stat("Page load (p75)", "Navigation duration: from request until the page finished loading. "
              "75% of page loads were at or below this." + RUM_SRC,
              [rum("A", "PerformanceNavigationDuration", "p75")], "ms", good_poor(3000, 6000),
              calc="mean", decimals=0, no_value=nv), 4),
        (stat("LCP (p75)", "Largest Contentful Paint: when the main content became visible. "
              "Good ≤ 2.5 s, poor > 4 s." + RUM_SRC,
              [rum("A", "WebVitalsLargestContentfulPaint", "p75")], "ms", good_poor(2500, 4000),
              calc="mean", decimals=0, no_value=nv), 4),
        (stat("CLS (p75)", "Cumulative Layout Shift: how much the page jumped while loading. "
              "Good ≤ 0.1, poor > 0.25." + RUM_SRC,
              [rum("A", "WebVitalsCumulativeLayoutShift", "p75")], "none", good_poor(0.1, 0.25),
              calc="mean", decimals=3, no_value=nv), 4),
        (stat("INP (p75)", "Interaction to Next Paint: delay between a click or tap and the page responding. "
              "Good ≤ 200 ms, poor > 500 ms." + RUM_SRC,
              [rum("A", "WebVitalsInteractionToNextPaint", "p75")], "ms", good_poor(200, 500),
              calc="mean", decimals=0, no_value=nv), 4),
        (stat("JavaScript errors", "Uncaught errors thrown in visitors' browsers." + RUM_SRC,
              [rum("A", "JsErrorCount", "Sum")], "short", ZERO_IS_GOOD, calc="sum", decimals=0,
              no_value=nv), 4),
    ], 4)
    lay.line([(series("Page views and browser errors (hourly)",
                      "Page views, JavaScript errors and failed requests made by the page, per hour." + RUM_SRC,
                      [rum("A", "PageViewCount", "Sum", label="Page views"),
                       rum("B", "JsErrorCount", "Sum", label="JS errors"),
                       rum("C", "HttpErrorCount", "Sum", label="HTTP errors")],
                      "short", draw="bars", no_value="No visits yet"), 24)], 7)


def delivery(lay, cfg):
    has_waf = "waf_acl" in cfg
    lay.row("Delivery · CloudFront")
    title_4xx = "4xx rate (incl. firewall blocks)" if has_waf else "4xx error rate"
    desc_4xx = ("Share of requests answered with a 4xx status (for example 403 or 404). "
                + ("This includes requests AWS WAF blocked (see Security) and bot requests for paths that "
                   "do not exist. " if has_waf else "Bots probing for missing files raise this. ")
                + "Use 5xx and availability to judge site health." + WEIGHTED + CF_SRC)
    lay.line([
        (stat("Requests", "Total requests CloudFront served in the selected range. Includes page assets and "
              "bots, so requests are not visitors." + CF_SRC,
              [cf("A", "Requests", "Sum")], "short", calc="sum", sparkline=True), 6),
        (stat("Data served", "Total bytes CloudFront sent to viewers in the selected range." + CF_SRC,
              [cf("A", "BytesDownloaded", "Sum")], "decbytes", calc="sum", sparkline=True), 6),
        (stat(title_4xx, desc_4xx, weighted_rate("4xxErrorRate"), "percent",
              good_poor(5, 10), decimals=2), 6),
        (stat("5xx error rate", "Share of requests answered with a 5xx status: CloudFront or the origin "
              "failed. Should stay near 0." + WEIGHTED + CF_SRC,
              weighted_rate("5xxErrorRate"), "percent", good_poor(0.5, 1), decimals=2), 6),
    ], 4)
    hourly = [cf("A", "Requests", "Sum", "60", hide=True),
              cf("B", "4xxErrorRate", "Average", "60", hide=True),
              cf("G", "5xxErrorRate", "Average", "60", hide=True),
              math("C", "$A * $B / 100"), math("H", "$A * $G / 100"),
              resample_sum("D", "C"), resample_sum("I", "H"), resample_sum("E", "A"),
              math("4xx", "$D / $E * 100", hide=False), math("5xx", "$I / $E * 100", hide=False)]
    named = [{"matcher": {"id": "byFrameRefID", "options": r},
              "properties": [{"id": "displayName", "value": r}]} for r in ("4xx", "5xx")]
    lay.line([
        (series("Requests over time", "Requests per period." + CF_SRC,
                [cf("A", "Requests", "Sum")], "short", draw="bars"), 12),
        (series("Error rates (hourly)", "Hourly share of requests returning 4xx and 5xx." + WEIGHTED + CF_SRC,
                hourly, "percent", overrides=named), 12),
    ], 8)
    lay.line([
        (series("Data served over time", "Bytes sent to viewers (downloaded) and received from them (uploaded)." + CF_SRC,
                [cf("A", "BytesDownloaded", "Sum", label="Downloaded"),
                 cf("B", "BytesUploaded", "Sum", label="Uploaded")], "decbytes"), 12),
        (text("About this data", about(cfg)), 12),
    ], 8)


def security(lay, cfg):
    regional = cfg.get("waf_region", "us-east-1") != "us-east-1"
    wf = lambda *a, **k: waf(*a, regional=regional, **k)  # noqa: E731
    ws = lambda *a, **k: waf_search(*a, regional=regional, **k)  # noqa: E731
    lay.row("Security · AWS WAF")
    share = [wf("A", "BlockedRequests", "Blocked", True), wf("B", "AllowedRequests", "Allowed", True),
             reduce_sum("C", "A"), reduce_sum("D", "B"), math("E", "$C / ($C + $D) * 100", hide=False)]
    lay.line([
        (stat("Blocked by firewall", "Requests AWS WAF stopped before they reached the site, answered with "
              "403. This is the firewall working, not the site failing." + WAF_SRC,
              [wf("A", "BlockedRequests", "Blocked")], "short", calc="sum", sparkline=True), 8),
        (stat("Allowed by firewall", "Requests WAF let through to the site. Includes bots the managed "
              "rules do not recognise." + WAF_SRC,
              [wf("A", "AllowedRequests", "Allowed")], "short", calc="sum", sparkline=True), 8),
        (stat("Share blocked", "Blocked ÷ (blocked + allowed) over the selected range." + WAF_SRC,
              share, "percent", decimals=1), 8),
    ], 4)
    lay.line([
        (series("Allowed vs blocked (hourly)", "Requests per hour by WAF decision." + WAF_SRC,
                [wf("A", "AllowedRequests", "Allowed"), wf("B", "BlockedRequests", "Blocked")],
                "short", draw="bars", stacked=True), 12),
        (top_table("Blocks by managed rule", "Which AWS managed rule matched blocked requests (for example path "
                   "traversal, missing user agent, exploitable paths, bad IP reputation)." + WAF_SRC,
                   ws("WebACL,ManagedRuleGroup,ManagedRuleGroupRule", "BlockedRequests",
                              "ManagedRuleGroupRule"), "Rule"), 12),
    ], 8)
    lay.line([
        (top_table("Blocked by country", "Countries the blocked requests came from, based on source IP." + WAF_SRC,
                   ws("WebACL,Country", "BlockedRequests", "Country"), "Country"), 8),
        (top_table("Allowed by country", "Countries of requests WAF allowed. Includes unrecognised bots, so it "
                   "approximates, not measures, visitor location." + WAF_SRC,
                   ws("WebACL,Country", "AllowedRequests", "Country"), "Country"), 8),
        (top_table("Blocked by attack type", "WAF's classification of blocked requests." + WAF_SRC,
                   ws("WebACL,Attack", "BlockedRequests", "Attack"), "Attack type"), 8),
    ], 8)


def traffic(lay):
    lay.row("Traffic · Application Load Balancer")
    lay.line([
        (stat("Requests", "Requests the load balancer received in the selected range. Includes bots." + ALB_SRC,
              [alb("A", "RequestCount", "Sum", "Requests")], "short", calc="sum", sparkline=True), 6),
        (stat("App 4xx responses", "Requests the app answered with a 4xx status (bad input, not found)." + ALB_SRC,
              [alb("A", "HTTPCode_Target_4XX_Count", "Sum", "4xx")], "short", calc="sum", decimals=0, no_value="None recorded"), 6),
        (stat("App 5xx responses", "Requests the app answered with a 5xx status: the app failed. Should be 0." + ALB_SRC,
              [alb("A", "HTTPCode_Target_5XX_Count", "Sum", "App 5xx")], "short", ZERO_IS_GOOD,
              calc="sum", decimals=0, no_value="None recorded"), 6),
        (stat("Load balancer 5xx", "5xx responses generated by the load balancer itself, usually because no "
              "healthy pod could answer (502/503/504). Should be 0." + ALB_SRC,
              [alb("A", "HTTPCode_ELB_5XX_Count", "Sum", "LB 5xx")], "short", ZERO_IS_GOOD,
              calc="sum", decimals=0, no_value="None recorded"), 6),
    ], 4)
    lay.line([
        (series("Requests and server errors", "Requests and 5xx responses per 5 minutes." + ALB_SRC,
                [alb("A", "RequestCount", "Sum", "Requests"),
                 alb("B", "HTTPCode_Target_5XX_Count", "Sum", "App 5xx"),
                 alb("C", "HTTPCode_ELB_5XX_Count", "Sum", "LB 5xx")], "short", draw="bars"), 12),
        (series("App response time", "Time from the load balancer sending a request to the app until the "
                "response started. Answers call Bedrock several times, so seconds are expected." + ALB_SRC,
                [alb("A", "TargetResponseTime", "Average", "Average"),
                 alb("B", "TargetResponseTime", "p90", "p90")], "s"), 12),
    ], 8)


def bedrock_section(lay, cfg):
    llm, embed = cfg["bedrock"]["llm"], cfg["bedrock"]["embed"]
    lay.row("AI · Amazon Bedrock")
    cost = cw_search("A", "${bedrock_region}",
                     f"FILL(SUM(SEARCH('{{AWS/Bedrock,ModelId}} MetricName=\"InputTokenCount\" ModelId=\"{llm}\"', 'Sum', 3600)), 0) / 1000 * ${{price_llm_in}}"
                     f" + FILL(SUM(SEARCH('{{AWS/Bedrock,ModelId}} MetricName=\"OutputTokenCount\" ModelId=\"{llm}\"', 'Sum', 3600)), 0) / 1000 * ${{price_llm_out}}"
                     f" + FILL(SUM(SEARCH('{{AWS/Bedrock,ModelId}} MetricName=\"InputTokenCount\" ModelId=\"{embed}\"', 'Sum', 3600)), 0) / 1000 * ${{price_embed_in}}",
                     "Estimated cost")
    lay.line([
        (stat("LLM calls", f"Converse calls to {llm}. One question makes several (rewrite, rerank, answer)." + BR_SRC,
              [bedrock("A", "Invocations", "Sum", llm, "LLM calls")], "short", calc="sum", decimals=0,
              sparkline=True), 4),
        (stat("Embedding calls", f"Calls to {embed}, which turns each search query into a vector." + BR_SRC,
              [bedrock("A", "Invocations", "Sum", embed, "Embedding calls")], "short", calc="sum",
              decimals=0, sparkline=True), 4),
        (stat("LLM input tokens", f"Tokens sent to {llm}: prompts, retrieved verses and instructions." + BR_SRC,
              [bedrock("A", "InputTokenCount", "Sum", llm, "Input tokens")], "short", calc="sum"), 4),
        (stat("LLM output tokens", f"Tokens {llm} generated." + BR_SRC,
              [bedrock("A", "OutputTokenCount", "Sum", llm, "Output tokens")], "short", calc="sum"), 4),
        (stat("LLM latency (p90)", f"90% of calls to {llm} finished within this time." + BR_SRC,
              [bedrock("A", "InvocationLatency", "p90", llm, "p90")], "ms", good_poor(5000, 15000),
              calc="mean", decimals=0), 4),
        (stat("Errors & throttles", "Client errors, server errors and throttled calls across all Bedrock "
              "models. Throttles mean a quota was hit. CloudWatch publishes these metrics only when one "
              "occurs, so \"None recorded\" means none in the selected range." + BR_SRC,
              [bedrock_search("A", ["InvocationClientErrors", "InvocationServerErrors", "InvocationThrottles"],
                              "Sum", "Errors")], "short", ZERO_IS_GOOD, calc="sum", decimals=0,
              no_value="None recorded"), 4),
    ], 4)
    per_model = cw_search("A", "${bedrock_region}",
                          "SEARCH('{AWS/Bedrock,ModelId} MetricName=\"Invocations\"', 'Sum', 3600)",
                          "${PROP('Dim.ModelId')}")
    lay.line([
        (series("Calls per model (hourly)", "Bedrock invocations per hour, per model." + BR_SRC,
                [per_model], "short", draw="bars", stacked=True), 8),
        (series("LLM tokens (hourly)", f"Input and output tokens per hour for {llm}." + BR_SRC,
                [bedrock("A", "InputTokenCount", "Sum", llm, "Input"),
                 bedrock("B", "OutputTokenCount", "Sum", llm, "Output")], "short", draw="bars",
                stacked=True), 8),
        (stat("Estimated Bedrock cost", "Tokens × the per-1K-token prices entered in the dashboard's price "
              "boxes (top of the page), prefilled from the AWS Price List for "
              f"{cfg['bedrock']['region']} (on-demand, 2026-09-26). An estimate: check AWS Billing for the actual "
              "charge." + BR_SRC,
              [cost], "currencyUSD", calc="sum", decimals=4), 8),
    ], 8)


def about(cfg):
    parts = [
        "**Signal type:** Measured. Every panel's ⓘ names its source.",
        f"**Site:** `https://{cfg['domain']}/`. {cfg['notes']}",
        f"**Availability:** Grafana Synthetic Monitoring check `{cfg['sm_job']}`, {cfg['sm_schedule']}.",
    ]
    if "rum_app" in cfg:
        parts.append(f"**Real visitors:** CloudWatch RUM app monitor `{cfg['rum_app']}` (no cookies, all sessions).")
    if "distribution" in cfg:
        parts.append(f"**Delivery:** CloudWatch `AWS/CloudFront` in `us-east-1`, distribution `{cfg['distribution']}`, "
                     "one-minute data points, usually a few minutes behind. Requests count every file fetched and "
                     "include bots, so they are not visitors.")
    if "alb" in cfg:
        parts.append(f"**Traffic:** CloudWatch `AWS/ApplicationELB` in `{cfg['region']}`, load balancer "
                     f"`{cfg['alb']}` (created by the Kubernetes ingress). Requests include bots.")
    if "bedrock" in cfg:
        b = cfg["bedrock"]
        parts.append(f"**AI:** CloudWatch `AWS/Bedrock` in `{b['region']}`: answers from `{b['llm']}`, search "
                     f"vectors from `{b['embed']}`. The cost panel multiplies tokens by the per-1K-token prices in "
                     "the boxes at the top of the page (from the AWS Price List, 2026-09-26; update them if prices change).")
    if "waf_acl" in cfg:
        parts.append(f"**Security:** AWS WAF web ACL `{cfg['waf_acl']}` ({cfg.get('waf_region', 'us-east-1')}). Blocked requests return 403 and are "
                     "also counted in the 4xx rate.")
    if "deploy_tags" in cfg:
        parts.append("**Deploy markers:** blue vertical lines, posted by the site's GitHub Actions deploy.")
    missing = []
    if "rum_app" not in cfg:
        missing.append("real-visitor data (no RUM on this site)")
    if "waf_acl" not in cfg:
        missing.append("firewall data (no AWS WAF in front of this site)")
    if "alb" in cfg:
        missing.append("pod CPU, memory and restarts (Container Insights is not enabled)")
    if "deploy_tags" not in cfg:
        missing.append("deploy markers")
    missing.append("request logs (not collected)")
    parts.append("**Not shown:** " + "; ".join(missing) + ".")
    return "\n\n".join(parts)


# ── Dashboards ───────────────────────────────────────────────────────────────

def datasource_vars():
    return [
        {"name": "datasource", "label": "CloudWatch", "type": "datasource", "query": "cloudwatch",
         "current": {}, "hide": 0},
        {"name": "prom", "label": "Prometheus", "type": "datasource", "query": "prometheus",
         "regex": "/grafanacloud-.*-prom/", "current": {}, "hide": 0},
    ]


def constant(name, label, value):
    return {"name": name, "label": label, "type": "constant", "query": value, "hide": 2}


def base(uid, title, description, tags, variables, panels, annotations=()):
    return {
        "uid": uid, "title": title, "description": description, "tags": tags,
        "timezone": "browser", "time": {"from": "now-7d", "to": "now"}, "refresh": "15m",
        "timepicker": {"refresh_intervals": ["15m", "30m", "1h"]},
        "schemaVersion": 39, "editable": True, "graphTooltip": 1,
        "templating": {"list": datasource_vars() + variables},
        "annotations": {"list": list(annotations)},
        "panels": panels,
    }


def domain_dashboard(cfg):
    lay = Layout()
    availability(lay)
    if "rum_app" in cfg:
        real_visitors(lay)
    if "distribution" in cfg:
        delivery(lay, cfg)
    if "alb" in cfg:
        traffic(lay)
    if "bedrock" in cfg:
        bedrock_section(lay, cfg)
    if "waf_acl" in cfg:
        security(lay, cfg)
    if "distribution" not in cfg:
        lay.line([(text("About this data", about(cfg)), 24)], 7)

    variables = [constant("sm_job", "Uptime check", cfg["sm_job"])]
    sections = ["Availability"]
    if "rum_app" in cfg:
        variables.append(constant("rum_app", "RUM app monitor", cfg["rum_app"]))
        sections.append("Visitors")
    if "distribution" in cfg:
        variables.append(constant("distribution", "Distribution", cfg["distribution"]))
        sections.append("Delivery")
    if "alb" in cfg:
        variables += [constant("alb", "Load balancer", cfg["alb"]), constant("region", "Region", cfg["region"])]
        sections.append("Traffic")
    if "bedrock" in cfg:
        variables.append(constant("bedrock_region", "Bedrock region", cfg["bedrock"]["region"]))
        prices = cfg["bedrock"]["prices"]
        variables += [price_box("price_llm_in", "LLM $ per 1K input tokens", prices["llm_in"]),
                      price_box("price_llm_out", "LLM $ per 1K output tokens", prices["llm_out"]),
                      price_box("price_embed_in", "Embedding $ per 1K tokens", prices["embed_in"])]
        sections.append("AI")
    if "waf_acl" in cfg:
        variables += [constant("waf_acl", "WAF web ACL", cfg["waf_acl"]),
                      constant("waf_region", "WAF region", cfg.get("waf_region", "us-east-1"))]
        sections.append("Security")

    annotations = []
    if "deploy_tags" in cfg:
        annotations.append({"name": "Deploys", "enable": True, "hide": False, "iconColor": "#8AB8FF",
                            "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                            "target": {"type": "tags", "tags": cfg["deploy_tags"],
                                       "matchAny": False, "limit": 100}})

    title = f"{cfg['domain']} · " + ", ".join(sections[:-1]) + " & " + sections[-1]
    tags = [cfg["domain"], "measured"] + (["cloudfront"] if "distribution" in cfg else []) \
        + (["bedrock"] if "bedrock" in cfg else [])
    return base(cfg["uid"], title, f"Monitoring for https://{cfg['domain']}/.", tags, variables,
                lay.panels, annotations)


def price_box(name, label, value):
    """A visible text box on the dashboard, prefilled from the AWS price list; editable in Grafana."""
    return {"name": name, "label": label, "type": "textbox", "query": value,
            "current": {"text": value, "value": value}, "hide": 0}


def overview_dashboard():
    lay = Layout()
    lay.add(text("", "One line per site. Open a site's own dashboard for detail. Every figure is measured; "
                     "\"No check\" means that site's uptime check is not set up yet."), 0, 24, 2, True)
    for cfg in DOMAINS:
        sel = f'job="{cfg["sm_job"]}"'
        link = [{"title": f"{cfg['domain']} dashboard", "url": f"/d/{cfg['uid']}"}]
        name = text("", f"### [{cfg['domain']}](/d/{cfg['uid']})\n{cfg['notes'].split(':')[0]}")
        if "distribution" in cfg:
            dist = cfg["distribution"]
            src = CF_SRC.replace("${distribution}", dist)
            requests = stat("Requests", f"Requests CloudFront served for {cfg['domain']} in the selected range. "
                            "Includes bots." + src,
                            [cf("A", "Requests", "Sum", dist=dist)], "short", calc="sum", sparkline=True)
            err5 = stat("5xx rate", f"Request-weighted 5xx rate for {cfg['domain']}." + WEIGHTED + src,
                        weighted_rate("5xxErrorRate", dist), "percent", good_poor(0.5, 1), decimals=2)
        else:
            src = ALB_SRC.replace("${region}", cfg["region"]).replace("${alb}", cfg["alb"])
            kw = {"name": cfg["alb"], "region": cfg["region"]}
            requests = stat("Requests", f"Requests the load balancer received for {cfg['domain']}. Includes bots." + src,
                            [alb("A", "RequestCount", "Sum", "Requests", **kw)], "short", calc="sum", sparkline=True)
            err5 = stat("5xx responses", f"App and load balancer 5xx responses for {cfg['domain']}." + src,
                        [alb_5xx_total("A", cfg["alb"], cfg["region"])],
                        "short", ZERO_IS_GOOD, calc="sum", decimals=0, no_value="None recorded")
        panels = [(name, 4), (status_now(sel), 4), (uptime(sel), 4), (check_duration(sel), 4),
                  (requests, 4), (err5, 4)]
        for panel, _ in panels[1:4]:
            panel["description"] = panel["description"].replace("${sm_job}", cfg["sm_job"])
        for panel, _ in panels[1:]:
            panel["links"] = link
        lay.line(panels, 4)
    return base("atla-in-overview", "atla.in sites · Overview",
                "Status, uptime, speed, traffic and server errors for every atla.in site.",
                ["atla.in", "overview", "measured"], [], lay.panels)


def main():
    OUT.mkdir(exist_ok=True)
    written = []
    for cfg in DOMAINS:
        written.append((f"{cfg['slug']}.json", domain_dashboard(cfg)))
    written.append(("overview.json", overview_dashboard()))
    for name, dash in written:
        (OUT / name).write_text(json.dumps(dash, indent=2, ensure_ascii=False) + "\n")
        print(f"{name}: {len(dash['panels'])} panels")


if __name__ == "__main__":
    main()
