from __future__ import annotations

import argparse, json, time

from .sync import run_sync
from dotenv import load_dotenv
load_dotenv()

def main() -> None:
    parser = argparse.ArgumentParser(description="IGAI sync runner")
    parser.add_argument("--state-file", default="sync.json")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--target-table", default="health_records")
    parser.add_argument("--qdrant-collection", default=None)
    parser.add_argument("--continuous", action="store_true", help="Keep syncing in a loop")
    parser.add_argument("--sleep-seconds", type=float, default=2.0, help="Delay between loop iterations")
    args = parser.parse_args()

    import traceback
    while True:
        try:
            result = run_sync(
                sync_state_path=args.state_file,
                batch_size=args.batch_size,
                target_table=args.target_table,
                qdrant_collection=args.qdrant_collection,
            )
            print(json.dumps(result, indent=2))
            if not args.continuous:
                break
            time.sleep(max(args.sleep_seconds, 0.0))
        except Exception as e:
            print(f"\n[ERROR] Unhandled exception during sync: {type(e).__name__}: {e}")
            print(traceback.format_exc())
            print(f"\nRetrying in 5 minutes (300 seconds)...")
            time.sleep(300)


if __name__ == "__main__":
    main()
