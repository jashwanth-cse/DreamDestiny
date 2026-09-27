"""
Dream Destiny — Unified Deployment Verification Test Suite
==========================================================
Tests all microservices through the single NGINX reverse proxy URL.

Usage:
    python deploy/verify_deployment.py [BASE_URL]

Examples:
    python deploy/verify_deployment.py http://localhost
    python deploy/verify_deployment.py http://54.210.12.34
    python deploy/verify_deployment.py https://api.yourdomain.com
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def check_endpoint(label: str, url: str, method: str = "GET", payload: dict = None, expected_statuses: tuple = (200,)):
    start_t = time.time()
    data_bytes = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if payload else {}

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            elapsed_ms = round((time.time() - start_t) * 1000)
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
            passed = status in expected_statuses
            tag = "[PASS]" if passed else "[FAIL]"
            print(f"{tag:<7} | {method:<4} | {status} | {elapsed_ms:>5}ms | {label:<22} -> {url}")
            return passed
    except urllib.error.HTTPError as e:
        elapsed_ms = round((time.time() - start_t) * 1000)
        passed = e.code in expected_statuses
        tag = "[PASS]" if passed else "[FAIL]"
        print(f"{tag:<7} | {method:<4} | {e.code} | {elapsed_ms:>5}ms | {label:<22} -> {url}")
        return passed
    except Exception as e:
        elapsed_ms = round((time.time() - start_t) * 1000)
        print(f"[FAIL]  | {method:<4} | ERR | {elapsed_ms:>5}ms | {label:<22} -> {url} ({e})")
        return False


def main():
    parser = argparse.ArgumentParser(description="Verify Dream Destiny Gateway Endpoints")
    parser.add_argument("url", nargs="?", default="http://localhost", help="Base URL of the reverse proxy (default: http://localhost)")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print("=" * 80)
    print(f"  DREAM DESTINY — DEPLOYMENT VERIFICATION TEST SUITE")
    print(f"  Target Gateway URL: {base_url}")
    print("=" * 80)
    print(f"{'STATUS':<7} | {'METH':<4} | CODE| {'LATENCY':>7} | {'SERVICE':<22} | URL")
    print("-" * 80)

    results = []

    # 1. Gateway Healthcheck
    results.append(check_endpoint("Gateway Health", f"{base_url}/health"))

    # 2. Tourism Service
    results.append(check_endpoint("Tourism Service", f"{base_url}/tourism?city=delhi&limit=3"))

    # 3. Hotel Service
    results.append(check_endpoint("Hotel Service", f"{base_url}/hotels?city=delhi&check_in=2026-10-15&check_out=2026-10-18&adults=2"))

    # 4. Route Service
    results.append(check_endpoint("Route Service", f"{base_url}/route?origin=delhi&destination=jaipur"))

    # 5. Bus Service
    results.append(check_endpoint(
        "Bus Service",
        f"{base_url}/api/v1/buses/search?source=delhi&destination=jaipur&journey_date=15-10-2026"
    ))

    # 6. Train Service
    results.append(check_endpoint("Train Service", f"{base_url}/api/v1/trains/search?from=delhi&to=mumbai&date=15-10-2026"))

    # 7. Flight Service
    results.append(check_endpoint(
        "Flight Service",
        f"{base_url}/flights/search",
        method="POST",
        payload={
            "origin": "delhi",
            "destination": "mumbai",
            "outbound_date": "2026-10-15",
            "travelers": 1
        }
    ))

    # 8. Planner Context Endpoint
    results.append(check_endpoint(
        "Planner Context",
        f"{base_url}/plan/context",
        method="POST",
        payload={
            "origin": "rajapalayam",
            "destination": "delhi",
            "start_date": "2026-10-15",
            "end_date": "2026-10-18",
            "travelers": 2,
            "preferences": {
                "budget": {"level": "medium"},
                "transport": {"mode": "train"},
                "hotel": {"category": "mid_range"}
            }
        }
    ))

    passed_count = sum(1 for r in results if r)
    total_count = len(results)

    print("-" * 80)
    print(f"Results: {passed_count}/{total_count} endpoints passed successfully.")
    print("=" * 80)

    if passed_count == total_count:
        print("[SUCCESS] All microservices are healthy, reachable, and correctly routed through NGINX!")
        sys.exit(0)
    else:
        print("[WARNING] Some endpoints failed or returned errors. Check microservice container logs.")
        sys.exit(1)


if __name__ == "__main__":
    main()
