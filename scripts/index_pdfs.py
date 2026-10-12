"""Create or refresh the local vector index for PDFs in data/pdfs."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="discard and recreate the PDF collection")
    args = parser.parse_args()
    try:
        from src.rag.indexer import index_pdfs

        result = index_pdfs(rebuild=args.rebuild)
    except (FileNotFoundError, ValueError) as error:
        print(f"Indexing failed: {error}", file=sys.stderr)
        return 1
    except ImportError as error:
        print(f"Missing RAG dependency: {error}. Install requirements.txt first.", file=sys.stderr)
        return 1

    for filename in result["indexed"]:
        print(f"Indexed {filename}")
    for filename in result["skipped"]:
        print(f"Unchanged, skipped: {filename}")
    if result["removed_chunks"]:
        print(f"Removed {result['removed_chunks']} chunks for deleted PDFs")
    print(f"Index ready: {result['total_chunks']} chunks in {result['index_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
