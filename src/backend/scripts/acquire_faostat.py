"""Acquire and validate an official annual Jamaica QCL dataset (cached by default)."""
import argparse
import json
from src.backend.app.agriculture.faostat_client import acquire_jamaica

if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--start",type=int,default=2016)
    parser.add_argument("--end",type=int,default=2025)
    parser.add_argument("--refresh",action="store_true")
    args = parser.parse_args()
    result = acquire_jamaica(args.start,args.end,args.refresh)
    summary = {k:v for k,v in result["validation"].items() if k not in {"items","item_year_coverage","series_gaps"}}
    summary["item_categories"] = len(result["validation"]["items"])
    print(json.dumps(summary,indent=2))
