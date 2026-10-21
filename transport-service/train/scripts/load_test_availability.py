"""
High-Concurrency Stress Testing Pipeline — Train Availability Microservice
Specifically tuned for Train 06030 (Tirunelveli -> Mettupalayam Special Express)

Runs on 5 Consecutive Sundays:
  - 25-10-2026
  - 01-11-2026
  - 08-11-2026
  - 15-11-2026
  - 22-11-2026

Classes:
  - SL (Sleeper)
  - 3A (3rd AC)
  - 2A (2nd AC)

Full 23-Station Sequential Route (253 forward station pairs):
  TEN  -> SMD  -> KIC  -> ASD  -> KKY  -> PCM  -> TSI  -> KDNL ->
  SNKL -> RJPM -> SVPR -> SVKS -> VPT  -> MDU  -> DG   -> ODC  ->
  PLNI -> UDT  -> POY  -> CNV  -> PTJ  -> CBE  -> MTP

Features:
  - Simulates up to 10,000 concurrent user queries
  - Scenario 1 ('same'): Concurrent users query the exact same hot payload (measures in-flight Singleflight coalescing)
  - Scenario 2 ('mixed'): Every query dynamically picks different stations along the route, different Sundays, and classes
  - Scenario 3 ('comparison'): Executes both scenarios and outputs the exact latency delay and speedup comparison
  - Measures percentiles: p50, p90, p95, p99, Min, Max, Average latency, and Throughput (RPS)

Usage:
  python scripts/load_test_availability.py --url http://127.0.0.1:8005 --requests 100 --concurrency 20 --mode same
  python scripts/load_test_availability.py --url http://127.0.0.1:8005 --requests 1000 --concurrency 100 --mode mixed
  python scripts/load_test_availability.py --url http://127.0.0.1:8005 --requests 500 --concurrency 50 --mode comparison
"""

import argparse
import asyncio
import random
import time
import statistics
from typing import List, Tuple, Dict, Any

import httpx

# Train 06030 Configuration
TRAIN_NO = "06030"

# 5 Consecutive Sundays for Train 06030
SUNDAY_DATES = [
    "25-10-2026",
    "01-11-2026",
    "08-11-2026",
    "15-11-2026",
    "22-11-2026",
]

# Travel Classes
TRAVEL_CLASSES = ["SL", "3A", "2A"]

# Complete 23 Intermediate Stations along the Train 06030 Route (in exact sequential order)
ROUTE_STATIONS = [
    "TEN",   # Tirunelveli (Origin)
    "SMD",   # Cheranmahadevi
    "KIC",   # Kallidaikurichi
    "ASD",   # Ambasamudram
    "KKY",   # Kilakadaiyam
    "PCM",   # Pavurchatram
    "TSI",   # Tenkasi Junction
    "KDNL",  # Kadayanallur
    "SNKL",  # Sankarankovil
    "RJPM",  # Rajapalayam
    "SVPR",  # Srivilliputtur
    "SVKS",  # Sivakasi
    "VPT",   # Virudhunagar Junction
    "MDU",   # Madurai Junction
    "DG",    # Dindigul Junction
    "ODC",   # Oddanchatram
    "PLNI",  # Palani
    "UDT",   # Udumalaipettai
    "POY",   # Pollachi Junction
    "CNV",   # Kinattukkadavu
    "PTJ",   # Podanur Junction
    "CBE",   # Coimbatore Junction
    "MTP",   # Mettupalayam (Destination)
]


def generate_random_forward_route() -> Tuple[str, str]:
    """Picks two stations where source appears strictly before destination."""
    i = random.randint(0, len(ROUTE_STATIONS) - 2)
    j = random.randint(i + 1, len(ROUTE_STATIONS) - 1)
    return ROUTE_STATIONS[i], ROUTE_STATIONS[j]


def build_payload(train_no: str, src: str, dst: str, cls: str, date: str) -> Dict[str, str]:
    return {
        "trainNo": train_no,
        "source": src,
        "destination": dst,
        "travelClass": cls,
        "date": date,
        "quota": "GN",
    }


async def worker(
    worker_id: int,
    base_url: str,
    queue: asyncio.Queue,
    results: List[Tuple[int, float]],
    client: httpx.AsyncClient,
    use_json_body: bool = True,
):
    while not queue.empty():
        try:
            payload = await queue.get()
        except asyncio.QueueEmpty:
            break

        url = f"{base_url}/api/v1/trains/availability"
        t0 = time.monotonic()
        try:
            if use_json_body:
                resp = await client.post(url, json=payload, timeout=20.0)
            else:
                resp = await client.post(url, params=payload, timeout=20.0)
            latency = (time.monotonic() - t0) * 1000
            results.append((resp.status_code, latency))
            if resp.status_code >= 400:
                print(f"  [ERROR {resp.status_code}] {payload['source']}->{payload['destination']} ({payload['travelClass']} on {payload['date']}): {resp.text[:120]}")
        except Exception as exc:
            latency = (time.monotonic() - t0) * 1000
            results.append((599, latency))
            print(f"  [CLIENT TIMEOUT/EXCEPTION] {payload['source']}->{payload['destination']} ({payload['travelClass']}): {exc}")
        finally:
            queue.task_done()


async def execute_benchmark(
    base_url: str,
    total_requests: int,
    concurrency: int,
    mode: str,
    use_json_body: bool = True,
) -> Dict[str, Any]:
    print("\n" + "=" * 75)
    print(f"Train 06030 Stress Test Benchmark — Concurrency & Delay Engine")
    print(f"Target URL:       {base_url}")
    print(f"Mode:             {mode.upper()}")
    print(f"Total Queries:    {total_requests}")
    print(f"Concurrency:      {concurrency} concurrent workers")
    print(f"Route Stations:   {len(ROUTE_STATIONS)} stations (253 forward pairs)")
    print(f"Sundays Tested:   {len(SUNDAY_DATES)} dates ({', '.join(SUNDAY_DATES[:2])}...)")
    print(f"Classes Tested:   {', '.join(TRAVEL_CLASSES)}")
    print("=" * 75)

    queue = asyncio.Queue()

    # Hot query for 'same' mode: TEN -> MTP on 25-10-2026, Sleeper Class
    hot_payload = build_payload(TRAIN_NO, "TEN", "MTP", "SL", "25-10-2026")

    for _ in range(total_requests):
        if mode == "same":
            queue.put_nowait(hot_payload)
        else:
            src, dst = generate_random_forward_route()
            cls = random.choice(TRAVEL_CLASSES)
            date = random.choice(SUNDAY_DATES)
            queue.put_nowait(build_payload(TRAIN_NO, src, dst, cls, date))

    results: List[Tuple[int, float]] = []

    # Dynamic limits matching concurrency
    limits = httpx.Limits(
        max_keepalive_connections=min(concurrency, 150),
        max_connections=min(concurrency * 2, 600)
    )

    async with httpx.AsyncClient(limits=limits) as client:
        start_time = time.monotonic()
        workers = [
            asyncio.create_task(worker(i, base_url, queue, results, client, use_json_body))
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
    min_lat = min(latencies) if latencies else 0
    max_lat = max(latencies) if latencies else 0
    rps = total_requests / total_time if total_time > 0 else 0

    print("-" * 50)
    print(f"Total Duration:        {total_time:.2f} s")
    print(f"Throughput:            {rps:.2f} req/sec")
    print(f"Success Count (2xx):    {len(successes)} ({len(successes)/total_requests*100:.1f}%)")
    print(f"Client Errors (4xx):    {len(client_errors)}")
    print(f"Server Errors (5xx):    {len(server_errors)}")
    print("-" * 50)
    print(f"Latency Min:           {min_lat:.2f} ms")
    print(f"Latency Avg:           {avg_lat:.2f} ms")
    print(f"Latency Median (p50):  {p50:.2f} ms")
    print(f"Latency 90th%  (p90):  {p90:.2f} ms")
    print(f"Latency 95th%  (p95):  {p95:.2f} ms")
    print(f"Latency 99th%  (p99):  {p99:.2f} ms")
    print(f"Latency Max:           {max_lat:.2f} ms")
    print("=" * 75)

    return {
        "mode": mode,
        "total_requests": total_requests,
        "concurrency": concurrency,
        "duration": total_time,
        "rps": rps,
        "success_rate": len(successes) / total_requests * 100,
        "min": min_lat,
        "max": max_lat,
        "p50": p50,
        "p90": p90,
        "p95": p95,
        "p99": p99,
        "avg": avg_lat,
    }


async def main():
    parser = argparse.ArgumentParser(description="Train 06030 Multi-Station Concurrency & Delay Benchmark")
    parser.add_argument("--url", default="http://127.0.0.1:8005", help="Microservice base URL (e.g. http://127.0.0.1:8005)")
    parser.add_argument("--requests", type=int, default=100, help="Total queries (simulate up to 10,000)")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent workers (users)")
    parser.add_argument(
        "--mode",
        choices=["same", "mixed", "comparison"],
        default="comparison",
        help="Stress mode: 'same' (singleflight test), 'mixed' (multi-station diverse queries), or 'comparison'"
    )
    parser.add_argument("--use-query-params", action="store_true", help="Send parameters as query string instead of JSON body")
    args = parser.parse_args()

    use_json = not args.use_query_params

    if args.mode == "comparison":
        print("\n>>> PHASE 1: Running Identical Payload Stress Test (TEN -> MTP, SL, 25-10-2026)")
        same_res = await execute_benchmark(args.url, args.requests, args.concurrency, "same", use_json)
        
        await asyncio.sleep(1.0)
        
        print("\n>>> PHASE 2: Running Mixed Payload Stress Test (23 stations, 5 Sundays, SL/3A/2A)")
        mixed_res = await execute_benchmark(args.url, args.requests, args.concurrency, "mixed", use_json)

        print("\n" + "#" * 78)
        print("PERFORMANCE DELAY & LATENCY COMPARISON ANALYSIS (Train 06030)")
        print("#" * 78)
        print(f"Metric                | Identical Payload (Singleflight) | Diverse Payloads (23 Stations)")
        print("-" * 78)
        print(f"Throughput (RPS)      | {same_res['rps']:>25.2f} req/s | {mixed_res['rps']:>22.2f} req/s")
        print(f"Average Latency       | {same_res['avg']:>25.2f} ms    | {mixed_res['avg']:>22.2f} ms")
        print(f"Median Latency (p50)  | {same_res['p50']:>25.2f} ms    | {mixed_res['p50']:>22.2f} ms")
        print(f"95th Percentile (p95) | {same_res['p95']:>25.2f} ms    | {mixed_res['p95']:>22.2f} ms")
        print(f"99th Percentile (p99) | {same_res['p99']:>25.2f} ms    | {mixed_res['p99']:>22.2f} ms")
        print(f"Max Latency           | {same_res['max']:>25.2f} ms    | {mixed_res['max']:>22.2f} ms")
        
        speedup = mixed_res['avg'] / same_res['avg'] if same_res['avg'] > 0 else 1.0
        saved_ms = mixed_res['avg'] - same_res['avg']
        print("-" * 78)
        print(f"Delay Saved:           {saved_ms:.2f} ms lower latency per request with Singleflight.")
        print(f"Efficiency Gain:       {speedup:.1f}x speedup on identical concurrent requests.")
        print("#" * 78)
    else:
        await execute_benchmark(args.url, args.requests, args.concurrency, args.mode, use_json)


if __name__ == "__main__":
    asyncio.run(main())
