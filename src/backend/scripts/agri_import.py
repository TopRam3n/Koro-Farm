"""Load agricultural reference data or import a local statistics file into the `agri` schema. Dry run by default.

  python -m src.backend.scripts.agri_import reference                       # what would be added (nothing written)
  python -m src.backend.scripts.agri_import reference --apply
  python -m src.backend.scripts.agri_import observations FILE.csv            # KoroFarm template (data/agriculture/templates)
  python -m src.backend.scripts.agri_import faostat FILE.csv --dataset QCL   # FAOSTAT normalized bulk CSV
  ... --apply                                                               # keep the result (licence must be APPROVED)

Never fetches anything from the internet: FILE is a local file someone retrieved and registered. Refuses
APP_ENV=production. Prints counts and validation issues only. See docs/integrations/AGRICULTURAL_DATA.md.
"""
import argparse
import json
import os
import sys
from pathlib import Path


def main(argv=None, env=None, session_factory=None) -> int:
    env = os.environ if env is None else env
    parser = argparse.ArgumentParser(description="Offline agricultural data import (dry run unless --apply)")
    parser.add_argument("kind", choices=["reference", "observations", "faostat"])
    parser.add_argument("file", nargs="?", type=Path)
    parser.add_argument("--dataset", help="FAOSTAT dataset code (QCL or PP)")
    parser.add_argument("--element-map", type=Path, help="reviewed FAOSTAT element map (default: data/agriculture/reference)")
    parser.add_argument("--version-label")
    parser.add_argument("--retrieval-url")
    parser.add_argument("--operator", default=env.get("USER") or env.get("USERNAME") or "unknown")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if env.get("APP_ENV", "").strip().lower() == "production":
        print("refusing to run against production from this tool", file=sys.stderr)
        return 2
    if args.kind != "reference" and (args.file is None or not args.file.is_file()):
        print("a local FILE is required", file=sys.stderr)
        return 2
    if args.kind == "faostat" and not args.dataset:
        print("--dataset is required for FAOSTAT files", file=sys.stderr)
        return 2
    from src.backend.app.agriculture import ingestion
    if session_factory is None:
        from src.backend.app.infrastructure.database.session import create_session_factory
        session_factory = create_session_factory()
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            print("the agri schema exists only on PostgreSQL (migration 0029)", file=sys.stderr)
            return 2
        try:
            if args.kind == "reference":
                result = {"mode": "APPLY" if args.apply else "DRY_RUN", "added": ingestion.load_reference(session, apply=args.apply)}
            elif args.kind == "observations":
                result = ingestion.import_observations(session, args.file, operator=args.operator, apply=args.apply,
                                                       version_label=args.version_label, retrieval_url=args.retrieval_url).as_dict()
            else:
                result = ingestion.import_faostat(session, args.file, dataset_code=args.dataset, operator=args.operator, apply=args.apply,
                                                  element_map=args.element_map, version_label=args.version_label,
                                                  retrieval_url=args.retrieval_url).as_dict()
        except ingestion.ImportRefused as exc:
            session.rollback()
            print(f"refused: {exc}", file=sys.stderr)
            return 1
        if args.apply:
            session.commit()
        else:
            session.rollback()
    print(json.dumps(result, indent=2, default=str))
    if not args.apply:
        print("dry run: nothing was changed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
