"""Import an official FAOSTAT normalized CSV, preserving annual granularity."""
import argparse
from src.backend.app.agriculture.faostat import write_import

if __name__ == "__main__":
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("csv")
    p.add_argument("--source-url",required=True)
    p.add_argument("--domain",choices=["QCL","PP"],required=True)
    p.add_argument("--output",default="data/agriculture/faostat/annual.json")
    a = p.parse_args()
    result = write_import(a.csv,a.source_url,a.domain,a.output)
    print(f"Imported {len(result['records'])} annual observations; {len(result['rejected'])} rejected cells")
