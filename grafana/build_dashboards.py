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
        "distribution": "E2OMRFTQ27WGMZ", "sm_job": "atla.in homepage",
        "waf_acl": "CreatedByCloudFront-14eef7b4", "rum_app": "atla-in",
        "deploy_tags": ["atla.in", "deploy"],
        "notes": "Portfolio: Next.js static export in S3 behind CloudFront (Free plan, AWS WAF included).",
    },
    {
        "slug": "aif-atla-in", "uid": "aif-atla-in", "domain": "aif.atla.in",
        "distribution": "E2A5DBVVXUZ6JO", "sm_job": "aif.atla.in homepage",
        "notes": "AIF-C01 study site: S3 website endpoint (us-east-1) behind CloudFront. No WAF.",
    },
    {
        "slug": "games-atla-in", "uid": "games-atla-in", "domain": "games.atla.in",
        "distribution": "E1HCLV5K7MXCST", "sm_job": "games.atla.in homepage",
        "notes": "Games site: S3 website endpoint (ap-south-1) behind CloudFront. No WAF.",
    },
    {
        "slug": "obs-atla-in", "uid": "obs-atla-in", "domain": "obs.atla.in",
        "distribution": "E2EXL4C10F3QBA", "sm_job": "obs.atla.in homepage",
        "notes": "Observability page: private S3 bucket behind CloudFront. No WAF.",
    },
]

CW = {"type": "cloudwatch", "uid": "${datasource}"}
PROM = {"type": "prometheus", "uid": "${prom}"}
EXPR = {"type": "__expr__", "uid": "__expr__"}

CF_SRC = " Measured · CloudWatch AWS/CloudFront (us-east-1) · distribution ${distribution}."
SM_SRC = " Measured · Grafana Synthetic Monitoring check \"${sm_job}\" (3 probes, every 5 minutes)."
WAF_SRC = " Measured · CloudWatch AWS/WAFV2 (us-east-1) · web ACL ${waf_acl}."
RUM_SRC = (" Measured · CloudWatch AWS/RUM (us-east-1) · app monitor ${rum_app}. "
           "Browsers of real visitors only; most bots do not run JavaScript.")
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


def waf(ref, metric, label, hide=False):
    return cw_metric(ref, "AWS/WAFV2", metric, "Sum", {"WebACL": "${waf_acl}", "Rule": "ALL"},
                     "3600", label, hide)


def waf_search(schema, metric, label_dim):
    expr = (f"SEARCH('{{AWS/WAFV2,{schema}}} MetricName=\"{metric}\" WebACL=\"${{waf_acl}}\"', "
            "'Sum', 3600)")
    return {"datasource": CW, "refId": "A", "queryMode": "Metrics", "metricQueryType": 0,
            "metricEditorMode": 1, "region": "us-east-1", "expression": expr, "id": "",
            "period": "3600", "label": "${PROP('Dim." + label_dim + "')}"}


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
    return stat(title, "Share of check runs that succeeded over the selected range, across all probes." + SM_SRC,
                [prom(f"sum(increase(probe_all_success_sum{{{sel}}}[$__range])) / "
                      f"sum(increase(probe_all_success_count{{{sel}}}[$__range]))", title)],
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


def security(lay):
    lay.row("Security · AWS WAF")
    share = [waf("A", "BlockedRequests", "Blocked", True), waf("B", "AllowedRequests", "Allowed", True),
             reduce_sum("C", "A"), reduce_sum("D", "B"), math("E", "$C / ($C + $D) * 100", hide=False)]
    lay.line([
        (stat("Blocked by firewall", "Requests AWS WAF stopped before they reached the site, answered with "
              "403. This is the firewall working, not the site failing." + WAF_SRC,
              [waf("A", "BlockedRequests", "Blocked")], "short", calc="sum", sparkline=True), 8),
        (stat("Allowed by firewall", "Requests WAF let through to CloudFront and S3. Includes bots the managed "
              "rules do not recognise." + WAF_SRC,
              [waf("A", "AllowedRequests", "Allowed")], "short", calc="sum", sparkline=True), 8),
        (stat("Share blocked", "Blocked ÷ (blocked + allowed) over the selected range." + WAF_SRC,
              share, "percent", decimals=1), 8),
    ], 4)
    lay.line([
        (series("Allowed vs blocked (hourly)", "Requests per hour by WAF decision." + WAF_SRC,
                [waf("A", "AllowedRequests", "Allowed"), waf("B", "BlockedRequests", "Blocked")],
                "short", draw="bars", stacked=True), 12),
        (top_table("Blocks by managed rule", "Which AWS managed rule matched blocked requests (for example path "
                   "traversal, missing user agent, exploitable paths, bad IP reputation)." + WAF_SRC,
                   waf_search("WebACL,ManagedRuleGroup,ManagedRuleGroupRule", "BlockedRequests",
                              "ManagedRuleGroupRule"), "Rule"), 12),
    ], 8)
    lay.line([
        (top_table("Blocked by country", "Countries the blocked requests came from, based on source IP." + WAF_SRC,
                   waf_search("WebACL,Country", "BlockedRequests", "Country"), "Country"), 8),
        (top_table("Allowed by country", "Countries of requests WAF allowed. Includes unrecognised bots, so it "
                   "approximates, not measures, visitor location." + WAF_SRC,
                   waf_search("WebACL,Country", "AllowedRequests", "Country"), "Country"), 8),
        (top_table("Blocked by attack type", "WAF's classification of blocked requests." + WAF_SRC,
                   waf_search("WebACL,Attack", "BlockedRequests", "Attack"), "Attack type"), 8),
    ], 8)


def about(cfg):
    parts = [
        "**Signal type:** Measured. Every panel's ⓘ names its source.",
        f"**Site:** `https://{cfg['domain']}/`. {cfg['notes']}",
        f"**Availability:** Grafana Synthetic Monitoring check `{cfg['sm_job']}`, every 5 minutes from 3 probes.",
    ]
    if "rum_app" in cfg:
        parts.append(f"**Real visitors:** CloudWatch RUM app monitor `{cfg['rum_app']}` (no cookies, all sessions).")
    parts.append(f"**Delivery:** CloudWatch `AWS/CloudFront` in `us-east-1`, distribution `{cfg['distribution']}`, "
                 "one-minute data points, usually a few minutes behind. Requests count every file fetched and "
                 "include bots, so they are not visitors.")
    if "waf_acl" in cfg:
        parts.append(f"**Security:** AWS WAF web ACL `{cfg['waf_acl']}`. Blocked requests return 403 and are "
                     "also counted in the 4xx rate.")
    if "deploy_tags" in cfg:
        parts.append("**Deploy markers:** blue vertical lines, posted by the site's GitHub Actions deploy.")
    missing = []
    if "rum_app" not in cfg:
        missing.append("real-visitor data (no RUM on this site)")
    if "waf_acl" not in cfg:
        missing.append("firewall data (no AWS WAF on this distribution)")
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
    delivery(lay, cfg)
    if "waf_acl" in cfg:
        security(lay)

    variables = [constant("distribution", "Distribution", cfg["distribution"]),
                 constant("sm_job", "Uptime check", cfg["sm_job"])]
    sections = ["Availability"]
    if "rum_app" in cfg:
        variables.append(constant("rum_app", "RUM app monitor", cfg["rum_app"]))
        sections.append("Visitors")
    sections.append("Delivery")
    if "waf_acl" in cfg:
        variables.append(constant("waf_acl", "WAF web ACL", cfg["waf_acl"]))
        sections.append("Security")

    annotations = []
    if "deploy_tags" in cfg:
        annotations.append({"name": "Deploys", "enable": True, "hide": False, "iconColor": "#8AB8FF",
                            "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                            "target": {"type": "tags", "tags": cfg["deploy_tags"],
                                       "matchAny": False, "limit": 100}})

    title = f"{cfg['domain']} · " + ", ".join(sections[:-1]) + " & " + sections[-1]
    return base(cfg["uid"], title, f"Monitoring for https://{cfg['domain']}/.",
                [cfg["domain"], "cloudfront", "measured"], variables, lay.panels, annotations)


def overview_dashboard():
    lay = Layout()
    lay.add(text("", "One line per site. Open a site's own dashboard for detail. Every figure is measured; "
                     "\"No check\" means that site's uptime check is not set up yet."), 0, 24, 2, True)
    for cfg in DOMAINS:
        sel = f'job="{cfg["sm_job"]}"'
        dist = cfg["distribution"]
        link = [{"title": f"{cfg['domain']} dashboard", "url": f"/d/{cfg['uid']}"}]
        name = text("", f"### [{cfg['domain']}](/d/{cfg['uid']})\n{cfg['notes'].split(':')[0]}")
        requests = stat("Requests", f"Requests CloudFront served for {cfg['domain']} in the selected range. "
                        "Includes bots." + CF_SRC.replace("${distribution}", dist),
                        [cf("A", "Requests", "Sum", dist=dist)], "short", calc="sum", sparkline=True)
        err5 = stat("5xx rate", f"Request-weighted 5xx rate for {cfg['domain']}." + WEIGHTED
                    + CF_SRC.replace("${distribution}", dist),
                    weighted_rate("5xxErrorRate", dist), "percent", good_poor(0.5, 1), decimals=2)
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
