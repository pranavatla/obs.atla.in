"""Tests for status/collect_status.py with fake Prometheus and CloudWatch sources."""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "status"))
import collect_status as cs  # noqa: E402

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


class FakeProm:
    def __init__(self, fail=False):
        self.fail, self.queries = fail, []

    def query(self, promql):
        self.queries.append(promql)
        if self.fail:
            raise RuntimeError("401 Unauthorized")
        jobs = [d["sm_job"] for d in cs.DOMAINS]
        if promql.startswith("min by"):
            return {j: (0.0 if j.startswith("games") else 1.0) for j in jobs}
        if "probe_duration_seconds" in promql:
            return {j: 0.25 for j in jobs}
        return {j: 0.999 for j in jobs}


class FakeCloudWatch:
    """Two minutes of CloudFront traffic: 100 requests at 0% errors, then 1 request at 100%."""

    def fetch(self, queries, start, end):
        t1, t2 = end - timedelta(minutes=2), end - timedelta(minutes=1)
        series = {"req": [(t1, 100.0), (t2, 1.0)], "e5": [(t1, 0.0), (t2, 100.0)],
                  "e4": [(t1, 0.0), (t2, 0.0)]}
        return {q["Id"]: series.get(q["Id"], [(t2, 2.0)]) for q in queries}


    def list_dimension_values(self, namespace, metric_name, dimension):
        return ["global.amazon.nova-2-lite-v1:0", "amazon.titan-embed-text-v2:0", "us.anthropic.claude-sonnet-4-6"]


class BrokenCloudWatch:
    def fetch(self, queries, start, end):
        raise RuntimeError("AccessDenied: cloudwatch:GetMetricData")

    def list_dimension_values(self, namespace, metric_name, dimension):
        raise RuntimeError("AccessDenied: cloudwatch:ListMetrics")


def site(data, domain):
    return next(s for s in data["sites"] if s["domain"] == domain)


def value(rec, key):
    return next(m["value"] for m in rec["metrics"] if m["key"] == key)


class SnapshotTest(unittest.TestCase):
    def test_every_site_and_status(self):
        data = cs.snapshot(FakeProm(), lambda region: FakeCloudWatch(), now=NOW)
        self.assertEqual([s["domain"] for s in data["sites"]], [d["domain"] for d in cs.DOMAINS])
        self.assertEqual(site(data, "atla.in")["status"], "up")
        self.assertEqual(site(data, "games.atla.in")["status"], "down")
        self.assertEqual(data["unavailable_sources"], [])
        self.assertEqual(data["generated_at"], "2026-09-26T12:00:00Z")

    def test_error_rate_is_weighted_by_requests(self):
        # Averaging the two minutes would say 50%; weighted it is 1 failure in 101 requests.
        data = cs.snapshot(FakeProm(), lambda region: FakeCloudWatch(), now=NOW)
        self.assertAlmostEqual(value(site(data, "atla.in"), "error_5xx_rate_7d"), 100 / 101)

    def test_units_are_converted(self):
        rec = site(cs.snapshot(FakeProm(), lambda region: FakeCloudWatch(), now=NOW), "atla.in")
        self.assertAlmostEqual(value(rec, "uptime_7d"), 99.9)
        self.assertAlmostEqual(value(rec, "check_duration_24h"), 250)

    def test_failed_sources_are_reported_not_guessed(self):
        data = cs.snapshot(FakeProm(fail=True), lambda region: BrokenCloudWatch(), now=NOW)
        rec = site(data, "atla.in")
        self.assertEqual(rec["status"], "unknown")
        self.assertIsNone(value(rec, "uptime_7d"))
        self.assertFalse(any(m["key"] == "requests_7d" for m in rec["metrics"]))
        self.assertTrue(any("AccessDenied" in e for e in data["unavailable_sources"]))
        self.assertTrue(any("401" in e for e in data["unavailable_sources"]))

    def test_missing_credentials(self):
        data = cs.snapshot(None, lambda region: FakeCloudWatch(), now=NOW)
        self.assertIn("uptime checks: Prometheus credentials not configured", data["unavailable_sources"])

    def test_bedrock_cost_uses_configured_prices(self):
        rec = site(cs.snapshot(FakeProm(), lambda region: FakeCloudWatch(), now=NOW), "gita.atla.in")
        prices = next(d for d in cs.DOMAINS if d["domain"] == "gita.atla.in")["bedrock"]["prices"]
        expected = 2 / 1000 * (float(prices["llm_in"]) + float(prices["llm_out"]) + float(prices["embed_in"]))
        self.assertAlmostEqual(value(rec, "bedrock_cost_7d"), round(expected, 4))

    def test_every_active_bedrock_model_is_listed(self):
        models = cs.snapshot(FakeProm(), lambda region: FakeCloudWatch(), now=NOW)["ai_models"]
        by_id = {(m["region"], m["model_id"]): m for m in models}
        nova = by_id[("ap-south-1", "global.amazon.nova-2-lite-v1:0")]
        self.assertEqual((nova["role"], nova["used_by"]), ("Text generation", ["gita.atla.in"]))
        self.assertIsNotNone(nova["cost_usd_7d"])
        claude = by_id[("ap-south-1", "us.anthropic.claude-sonnet-4-6")]
        self.assertEqual(claude["used_by"], [])
        self.assertIsNone(claude["cost_usd_7d"])  # no price configured: never guessed

    def test_model_discovery_falls_back_to_configured_models(self):
        data = cs.snapshot(FakeProm(), lambda region: BrokenCloudWatch(), now=NOW)
        self.assertTrue(any("model discovery" in e and "ListMetrics" in e for e in data["unavailable_sources"]))

    def test_promql_escapes_dots_in_job_names(self):
        prom = FakeProm()
        cs.snapshot(prom, lambda region: FakeCloudWatch(), now=NOW)
        self.assertIn('job=~"atla\\\\.in homepage|', prom.queries[0])

    def test_hourly_buckets(self):
        pts = [(NOW - timedelta(minutes=30), 5.0), (NOW - timedelta(hours=23, minutes=30), 2.0),
               (NOW - timedelta(hours=30), 9.0)]
        buckets = cs.hourly(pts, NOW)
        self.assertEqual((len(buckets), buckets[0], buckets[-1], sum(buckets)), (24, 2.0, 5.0, 7.0))


if __name__ == "__main__":
    unittest.main()
