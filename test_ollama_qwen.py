"""
Test Ollama Qwen 2.5 Itinerary Generation
=========================================
Runs the raw Planning Agent prompt through a local Ollama instance running Qwen 2.5.

Usage:
    python test_ollama_qwen.py [--model qwen2.5:7b] [--host http://localhost:11434]
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Test Ollama Qwen 2.5 with Dream Destiny Itinerary Prompt")
    parser.add_argument("--model", default="qwen2.5:7b", help="Ollama model tag (e.g., qwen2.5:7b, qwen2.5:14b, qwen2.5:latest)")
    parser.add_argument("--host", default="http://localhost:11434", help="Ollama API base URL")
    args = parser.parse_args()

    # Load prompt bundle
    try:
        with open("raw_prompt_bundle.json", "r", encoding="utf-8") as f:
            bundle = json.load(f)
    except FileNotFoundError:
        print("[ERROR] raw_prompt_bundle.json not found. Run the extraction script first.")
        sys.exit(1)

    system_prompt = bundle["system_prompt"]
    user_content = bundle["user_content"]
    schema = bundle["schema"]

    print("=" * 65)
    print("  Testing Local Ollama with Qwen 2.5")
    print(f"  Model : {args.model}")
    print(f"  Host  : {args.host}")
    print("=" * 65)

    # Check Ollama connection & available models
    try:
        req = urllib.request.Request(f"{args.host}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            tags_data = json.loads(resp.read().decode("utf-8"))
            available = [m.get("name") for m in tags_data.get("models", [])]
            print(f"\n[OK] Connected to Ollama. Installed models: {available}")
            if not any(args.model in m for m in available):
                print(f"[WARNING] Model '{args.model}' not found in installed models.")
                print(f"To download it, run: ollama pull {args.model}")
    except Exception as e:
        print(f"\n[ERROR] Could not connect to Ollama at {args.host}: {e}")
        print("Please ensure Ollama is installed and running (`ollama serve`).")
        print("\nYou can still inspect the raw prompts saved in:")
        print("  - prompt_system.txt")
        print("  - prompt_user.txt")
        print("  - prompt_combined.txt")
        print("  - schema_itinerary.json")
        sys.exit(1)

    # Prepare chat request payload
    # Ollama /api/chat supports structured JSON output via the 'format' parameter (JSON schema)
    payload = {
        "model": args.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "format": schema,  # Ollama 0.5+ accepts full JSON schema
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_ctx": 16384  # Qwen 2.5 supports up to 32k/128k context; prompt is ~6k tokens
        }
    }

    req = urllib.request.Request(
        f"{args.host}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    print(f"\nSending planning prompt to {args.model} (this may take 15-60s depending on GPU/CPU)...")
    start_t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"\n[HTTP Error {e.code}]: {e.read().decode('utf-8')}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[Request Error]: {e}")
        sys.exit(1)

    elapsed = time.time() - start_t
    print(f"Done in {elapsed:.1f}s!\n")

    message_content = res_data.get("message", {}).get("content", "")
    try:
        itinerary = json.loads(message_content)
        print("=" * 65)
        print("  OUTPUT VALIDATION: SUCCESSFUL JSON PARSE")
        print("=" * 65)
        
        # Save output
        with open("ollama_qwen_output.json", "w", encoding="utf-8") as out_f:
            json.dump(itinerary, out_f, indent=2, ensure_ascii=False)
        print("Saved raw output to ollama_qwen_output.json\n")

        # Quick preview
        summary = itinerary.get("summary", {})
        print(f"Trip: {summary.get('origin')} -> {summary.get('destination')}")
        print(f"Days: {summary.get('days')} | Budget: {summary.get('budget_level')} | Pace: {summary.get('pace')}")
        
        ob = itinerary.get("outbound_transport", {})
        print(f"\nOutbound Transport:")
        print(f"  Instruction : {ob.get('instruction')}")
        print(f"  Direct      : {ob.get('is_direct')}")
        print(f"  Station     : {ob.get('departure_station')} -> {ob.get('arrival_station')}")
        print(f"  Train/Flight: {ob.get('train_number') or ob.get('flight_number')} - {ob.get('train_name') or ob.get('airline')}")
        print(f"  Schedule    : {ob.get('departure_date')} @ {ob.get('departure_time')} -> {ob.get('arrival_date')} @ {ob.get('arrival_time')}")
        
        print("\nDay-by-Day Summary:")
        for day in itinerary.get("days", []):
            print(f"  Day {day.get('day_number')} ({day.get('date')}): {day.get('theme')}")
            for act in day.get("activities", []):
                print(f"    - {act.get('start_time')} {act.get('name')} ({act.get('duration_minutes')} min)")

    except json.JSONDecodeError:
        print("[ERROR] Output was not valid JSON:")
        print(message_content[:1000])


if __name__ == "__main__":
    main()
