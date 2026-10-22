"""Normalize cached original Ministry tables and quarantine disagreements."""
import json
from app.agriculture.ingestion import build_dataset

if __name__ == "__main__":
    report = build_dataset()
    print(json.dumps({k: report[k] for k in ["validated_counts", "conflicts", "gaps", "sanity_checks_passed"]}, indent=2))
