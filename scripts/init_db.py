"""Creates the F1 database: downloads (or reads from cache) the real data and loads it into SQLite.

Usage (from the repo root):
    python scripts/init_db.py              # download what is missing and rebuild the DB
    python scripts/init_db.py --offline    # use only the local cache (data/raw/jolpica)
    python scripts/init_db.py --refresh    # ignore the cache and download everything again

A full first download is ~550 requests; the API limits to ~500/hour, so it may pause by itself (429)
and retry. It is safe to stop with Ctrl+C and run again: the cache is reused.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.database.builder import build_database  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="do not use the network; local cache only")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and download again")
    args = ap.parse_args()

    counts = build_database(offline=args.offline, refresh=args.refresh)
    print(f"\nDatabase created at {config.DB_PATH}")
    for table, n in counts.items():
        print(f"  {table:<22}{n:>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
