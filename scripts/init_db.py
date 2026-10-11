"""Crea la base de datos de F1: descarga (o lee de caché) los datos reales y los carga en SQLite.

Uso (desde la raíz del repo):
    python scripts/init_db.py              # descarga lo que falte y reconstruye la BD
    python scripts/init_db.py --offline    # usa solo la caché local (data/raw/jolpica)
    python scripts/init_db.py --refresh    # ignora la caché y vuelve a descargar todo

La primera descarga completa son ~550 requests; la API limita a ~500/hora, por lo que puede
pausarse sola (429) y reintentar. Es seguro cortar con Ctrl+C y volver a correr: la caché se reutiliza.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.database.builder import build_database  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="no usar la red; solo la caché local")
    ap.add_argument("--refresh", action="store_true", help="ignorar la caché y volver a descargar")
    args = ap.parse_args()

    counts = build_database(offline=args.offline, refresh=args.refresh)
    print(f"\nBase creada en {config.DB_PATH}")
    for table, n in counts.items():
        print(f"  {table:<22}{n:>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
