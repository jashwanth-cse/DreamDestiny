"""
Dream Destiny — Unified Deployment Verification Test Suite
==========================================================
Tests all microservices through the single NGINX reverse proxy URL
using fast, zero-quota internal /health probes.

If any endpoint fails or is unhealthy, automatically captures and prints
the target Docker container's recent logs to immediately diagnose failures.

Usage:
    python deploy/verify_deployment.py [BASE_URL] [--deep]

Examples:
    python deploy/verify_deployment.py http://localhost
    python deploy/verify_deployment.py http://3.110.43.124
    python deploy/verify_deployment.py http://localhost --deep
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


SERVICES = [
    {
        "label": "Gateway Health",
        "path": "/health",
        "container": "dream-destiny-gateway",
    },
    {
        "label": "Tourism Service",
        "path": "/tourism/health",
        "container": "dream-destiny-tourism",
    },
    {
        "label": "Hotel Service",
        "path": "/hotels/health",
        "container": "dream-destiny-hotel",
    },
    {
        "label": "Route Service",
        "path": "/route/health",
        "container": "dream-destiny-route",
    },
    {
        "label": "Bus Service",
        "path": "/api/v1/buses/health",
        "container": "dream-destiny-bus",
    },
    {
        "label": "Train Service",
        "path": "/api/v1/trains/health",
        "container": "dream-destiny-train",
    },
    {
        "label": "Flight Service",
        "path": "/flights/health",
        "container": "dream-destiny-flight",
    },
    {
        "label": "Planner Service",
        "path": "/plan/health",
        "container": "dream-destiny-planner",
    },
]


def print_container_logs(container_name: str, lines: int = 30):
    """If docker is available and reachable locally, print recent logs for the failed container."""
    if not shutil.which("docker"):
        return

    try:
        res = subprocess.run(
            ["docker", "logs", "--tail", str(lines), container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            output = res.stdout.strip()
            print(f"\n{'!' * 20} RECENT CONTAINER LOGS: {container_name} {'!' * 20}")
            if output:
                print(output)
            else:
                print(f"(No log output recorded for {container_name})")
            print(f"{'!' * 70}\n")
    except Exception:
        pass


def check_endpoint(label: str, url: str, method: str = "GET", payload: dict = None, expected_statuses: tuple = (200,)):
    start_t = time.time()
    data_bytes = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if payload else {}

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            elapsed_ms = round((time.time() - start_t) * 1000)
            status = resp.status
            passed = status in expected_statuses
            tag = "[PASS]" if passed else "[FAIL]"
            print(f"{tag:<7} | {method:<4} | {status} | {elapsed_ms:>5}ms | {label:<22} -> {url}")
            return passed, None
    except urllib.error.HTTPError as e:
        elapsed_ms = round((time.time() - start_t) * 1000)
        passed = e.code in expected_statuses
        tag = "[PASS]" if passed else "[FAIL]"
        print(f"{tag:<7} | {method:<4} | {e.code} | {elapsed_ms:>5}ms | {label:<22} -> {url}")
        return passed, f"HTTP {e.code}"
    except Exception as e:
        elapsed_ms = round((time.time() - start_t) * 1000)
        print(f"[FAIL]  | {method:<4} | ERR | {elapsed_ms:>5}ms | {label:<22} -> {url} ({e})")
        return False, str(e)


def run_deep_checks(base_url: str):
    """Optional deeper integration checks with mock/sample payloads."""
    print("\nRunning optional deep integration validation...")
    print("-" * 80)
    check_endpoint(
        "Planner Context",
        f"{base_url}/plan/context",
        method="POST",
        payload={
            "origin": "delhi",
            "destination": "jaipur",
            "start_date": "2026-10-15",
            "end_date": "2026-10-18",
            "travelers": 2,
            "preferences": {
                "budget": {"level": "medium"},
                "transport": {"mode": "train"},
                "hotel": {"category": "mid_range"},
            },
        },
    )


def main():
    parser = argparse.ArgumentParser(description="Verify Dream Destiny Gateway Endpoints")
    parser.add_argument("url", nargs="?", default="http://localhost", help="Base URL of the reverse proxy (default: http://localhost)")
    parser.add_argument("--deep", action="store_true", help="Run deep data endpoints in addition to health probes")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    print("=" * 80)
    print(f"  DREAM DESTINY — DEPLOYMENT HEALTH VERIFICATION")
    print(f"  Target Gateway URL: {base_url}")
    print("=" * 80)
    print(f"{'STATUS':<7} | {'METH':<4} | CODE| {'LATENCY':>7} | {'SERVICE':<22} | URL")
    print("-" * 80)

    failed_containers = []
    passed_count = 0

    for svc in SERVICES:
        full_url = f"{base_url}{svc['path']}"
        passed, err = check_endpoint(svc["label"], full_url)
        if passed:
            passed_count += 1
        else:
            failed_containers.append((svc["label"], svc["container"]))

    total_count = len(SERVICES)
    print("-" * 80)
    print(f"Results: {passed_count}/{total_count} healthchecks passed.")
    print("=" * 80)

    if failed_containers:
        print(f"\n[WARNING] {len(failed_containers)} service(s) failed health check!")
        for label, container in failed_containers:
            print(f"- {label} (container: {container})")
            print_container_logs(container, lines=30)
        sys.exit(1)

    print("[SUCCESS] All microservices are healthy, reachable, and correctly routed through NGINX!")

    if args.deep:
        run_deep_checks(base_url)

    sys.exit(0)


if __name__ == "__main__":
    main()
