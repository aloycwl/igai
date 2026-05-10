from __future__ import annotations
from dotenv import load_dotenv
from .sync import run_sync

import json, time, traceback

load_dotenv()

def main() -> None:
    processed = 0

    while processed < 20000:
        try:
            result = run_sync(
                sync_state_path="sync.json",
                batch_size=200,
                target_table="health_records",
                qdrant_collection="health_embeddings",
            )

            print(json.dumps(result, indent=2))

            synced = int(result.get("synced", 0))
            processed += synced

            print(
                json.dumps(
                    {"processed_total": processed, "max_records": 20000},
                    indent=2,
                )
            )

            if synced == 0:
                print("No more records found. Exiting.")
                break

            time.sleep(max(0, 0.0))

        except Exception as e:
            print(f"\n[ERROR] Unhandled exception during sync: {type(e).__name__}: {e}")
            print(traceback.format_exc())
            print("\nRetrying in 5 minutes (300 seconds)...")
            time.sleep(300)

    print(f"Finished processing. Total processed: {processed}")


if __name__ == "__main__":
    main()