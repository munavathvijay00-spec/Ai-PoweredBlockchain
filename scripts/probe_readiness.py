"""Conservative, read-only endpoint reliability probe.

Usage: python -m scripts.probe_readiness --base https://example.org --samples 8
No keys or write requests required. This is NOT a scale/load test.
"""
import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def probe(base, path, timeout):
    started = time.perf_counter()
    status, error = None, None
    try:
        with urlopen(Request(base.rstrip("/") + path, headers={"User-Agent": "ChainScope-readonly-probe/1"}), timeout=timeout) as response:
            status = response.status
            payload = response.read(500_000)
            json.loads(payload)
    except HTTPError as exc:
        status, error = exc.code, type(exc).__name__
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        error = type(exc).__name__
    return {"status": status, "ok": status == 200 and error is None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2), "error": error}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="API origin, without trailing path")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=8)
    args = parser.parse_args()
    if not 1 <= args.samples <= 20:
        parser.error("--samples must be between 1 and 20")
    if not args.base.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        parser.error("Use HTTPS for remote hosts")
    outcomes = {}
    for endpoint in ("/api/coverage", "/api/stats"):
        results = []
        for index in range(args.samples):
            results.append(probe(args.base, endpoint, args.timeout))
            if index + 1 < args.samples:
                time.sleep(0.5)
        good = sorted(row["latency_ms"] for row in results if row["ok"])
        outcomes[endpoint] = {
            "samples": len(results), "success_count": len(good),
            "success_rate": len(good) / len(results),
            "p50_ms_success_only": statistics.median(good) if good else None,
            "p95_ms_success_only": good[max(0, int((len(good) - 1) * .95))] if good else None,
            "responses": results,
        }
    print(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(),
                      "purpose": "read_only_sample_probe_not_load_test",
                      "measurement_note": "Small sample, sequential requests; no uptime or production SLA inference.",
                      "endpoints": outcomes}, indent=2))
    return 0 if all(x["success_rate"] == 1 for x in outcomes.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
