#!/usr/bin/env python3
"""Small dependency-free load/chaos harness for the clustered review queue.

Examples:
  python scripts/review_queue_load_test.py https://host.example/api --requests 5022 --concurrency 100
  python scripts/review_queue_load_test.py https://host.example/api --requests 500 --concurrency 100 --chaos-rate 0.10

The chaos mode intentionally aborts a percentage of client reads after opening the
request. It validates that the server remains responsive to subsequent requests;
it does not mutate or terminate the production service.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request


def fetch(base: str, index: int, chaos_rate: float) -> tuple[bool, float, str]:
    query = urllib.parse.urlencode({
        "limit": 100,
        "offset": (index % 50) * 100,
        "sort": "risk_desc",
        "clustered": "true",
    })
    url = f"{base.rstrip('/')}/transaction-browser?{query}"
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            if random.random() < chaos_rate:
                response.close()
                return True, time.perf_counter() - started, "client-abort"
            body = response.read()
            payload = json.loads(body)
            valid = response.status == 200 and isinstance(payload.get("transactions"), list)
            return valid, time.perf_counter() - started, str(response.status)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return False, time.perf_counter() - started, type(error).__name__


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", help="API root, for example https://host/api")
    parser.add_argument("--requests", type=int, default=5022)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--chaos-rate", type=float, default=0.0)
    parser.add_argument("--max-p95-ms", type=float, default=2500.0)
    parser.add_argument("--min-success-rate", type=float, default=0.99)
    args = parser.parse_args()

    started = time.perf_counter()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(fetch, args.base_url, i, args.chaos_rate) for i in range(args.requests)]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    elapsed = time.perf_counter() - started
    latencies = sorted(latency for _, latency, _ in results)
    successes = sum(1 for ok, _, _ in results if ok)
    success_rate = successes / len(results) if results else 0.0
    p50 = statistics.median(latencies) * 1000 if latencies else 0.0
    p95_index = min(len(latencies) - 1, max(0, int(len(latencies) * 0.95) - 1)) if latencies else 0
    p95 = latencies[p95_index] * 1000 if latencies else 0.0
    rps = len(results) / elapsed if elapsed else 0.0

    print(json.dumps({
        "requests": len(results),
        "concurrency": args.concurrency,
        "chaos_rate": args.chaos_rate,
        "successes": successes,
        "success_rate": round(success_rate, 4),
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "throughput_rps": round(rps, 1),
        "elapsed_s": round(elapsed, 2),
    }, indent=2))

    if success_rate < args.min_success_rate:
        print(f"FAIL: success rate {success_rate:.2%} < {args.min_success_rate:.2%}")
        return 1
    if p95 > args.max_p95_ms:
        print(f"FAIL: p95 {p95:.1f}ms > {args.max_p95_ms:.1f}ms")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
