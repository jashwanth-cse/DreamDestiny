"""
Repeatable Load Testing & Concurrency Benchmark for Train Availability Microservice

Tests:
  - High concurrency throughput (e.g., 50-100 concurrent workers)
  - In-flight request coalescing (duplicate request suppression)
  - Latency distribution (p50, p90, p95, p99)
  - Error rate under concurrent load

Usage:
  python scripts/load_test_availability.py --url http://127.0.0.1:8005 --requests 100 --concurrency 20
"""

import argparse
import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import List, Tuple
import statistics

import httpx


SAMPLE_TRAINS = [
    ("16102", "RJPM", "SVKS", "SL"),
    ("12626", "NDLS", "MAS", "3A"),
    ("12952", "NDLS", "MMCT", "2A"),
    ("12302", "NDLS", "HWH", "3A"),
    ("12164", "MAS", "CSMT", "SL"),
]


async def worker(
    name: int,
    base_url: str,
    queue: asyncio.Queue,
    results: List[Tuple[int, float]],
    client: httpx.AsyncClient,
    date_str: str,
):
    while not queue.empty():
        try:
            train_no, src, dst, cls = await queue.get()
        except asyncio.QueueEmpty:
            break

        url = f"{base_url}/api/v1/trains/availability"
        params = {
            "trainNo": train_no,
            "source": src,
            "destination": dst,
            "travelClass": cls,
            "date": date_str,
            "quota": "GN",
        }

        t0 = time.monotonic()
        try:
            resp = await client.post(url, params=params, timeout=10.0)
            latency = (time.monotonic() - t0) * 1000
            results.append((resp.status_code, latency))
        except Exception as exc:
            latency = (time.monotonic() - t0) * 1000
            results.append((599, latency))
        finally:
            queue.task_done()


async def run_load_test(base_url: str, total_requests: int, concurrency: int, duplicate_ratio: float = 0.7):
    print("=" * 65)
    print(f"Train Availability Microservice — Load Test Benchmark")
    print(f"Target URL:    {base_url}")
    print(f"Total Queries: {total_requests}")
    print(f"Concurrency:   {concurrency}")
    print(f"Dup Ratio:     {duplicate_ratio * 100:.0f}% (Testing In-Flight Coalescing)")
    print("=" * 65)

    date_str = (datetime.now() + timedelta(days=15)).strftime("%d-%m-%Y")
    queue = asyncio.Queue()

    # Pre-populate queue with mix of identical and diverse requests
    hot_train = SAMPLE_TRAINS[0]
    for _ in range(total_requests):
        if random.random() < duplicate_ratio:
            queue.put_nowait(hot_train)
        else:
            queue.put_nowait(random.choice(SAMPLE_TRAINS))

    results: List[Tuple[int, float]] = []

    limits = httpx.Limits(max_keepalive_connections=concurrency, max_connections=concurrency * 2)
    async with httpx.AsyncClient(limits=limits) as client:
        start_time = time.monotonic()
        workers = [
            asyncio.create_task(worker(i, base_url, queue, results, client, date_str))
            for i in range(concurrency)
        ]
        await queue.join()
        for w in workers:
            w.cancel()
        total_time = time.monotonic() - start_time

    # Compute metrics
    latencies = [lat for _, lat in results]
    status_codes = [status for status, _ in results]
    successes = [s for s in status_codes if 200 <= s < 300]
    server_errors = [s for s in status_codes if 500 <= s <= 599]
    client_errors = [s for s in status_codes if 400 <= s < 500]

    latencies.sort()
    p50 = statistics.median(latencies) if latencies else 0
    p90 = latencies[int(len(latencies) * 0.90)] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
    avg_lat = statistics.mean(latencies) if latencies else 0
    rps = total_requests / total_time if total_time > 0 else 0

    print("\nBenchmark Results Summary:")
    print("-" * 40)
    print(f"Total Duration:     {total_time:.2f} s")
    print(f"Throughput:         {rps:.2f} req/sec")
    print(f"Success Count (2xx): {len(successes)} ({len(successes)/total_requests*100:.1f}%)")
    print(f"Client Errors (4xx): {len(client_errors)}")
    print(f"Server Errors (5xx): {len(server_errors)}")
    print("-" * 40)
    print(f"Latency Avg:        {avg_lat:.2f} ms")
    print(f"Latency p50:        {p50:.2f} ms")
    print(f"Latency p90:        {p90:.2f} ms")
    print(f"Latency p95:        {p95:.2f} ms")
    print(f"Latency p99:        {p99:.2f} ms")
    print(f"Latency Max:        {max(latencies):.2f} ms" if latencies else "N/A")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Availability Load Tester")
    parser.add_argument("--url", default="http://127.0.0.1:8005", help="Base URL of service")
    parser.add_argument("--requests", type=int, default=50, help="Total number of requests")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent workers")
    args = parser.parse_args()

    asyncio.run(run_load_test(args.url, args.requests, args.concurrency))
