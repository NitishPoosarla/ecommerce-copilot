"""
STEP 6 runner: execute every query in sql/*.sql, print results, save outputs.
Run:  ./venv/Scripts/python.exe scripts/run_queries.py
Outputs go to sql/results/ as .txt (readable) and .csv (for dashboards).
Exit code 0 = all 15 queries ran; 1 = at least one failed.
"""
import glob
import os
import sys

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv


def get_engine():
    load_dotenv()
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    else:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return sa.create_engine(url)


def main():
    eng = get_engine()
    files = sorted(glob.glob("sql/*.sql"))
    if not files:
        sys.exit("ERROR: no .sql files found in sql/")
    outdir = "sql/results"
    os.makedirs(outdir, exist_ok=True)

    failures = []
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        sql = open(path, encoding="utf-8").read()
        try:
            df = pd.read_sql(sql, eng)
        except Exception as e:
            failures.append(name)
            print(f"[FAIL] {name}: {e}")
            continue
        # save readable + machine-readable outputs
        with open(os.path.join(outdir, f"{name}.txt"), "w", encoding="utf-8") as fh:
            fh.write(df.to_string(index=False))
        df.to_csv(os.path.join(outdir, f"{name}.csv"), index=False)
        print(f"[OK] {name:<45} {len(df)} rows")
        if len(df) <= 15:
            print(df.to_string(index=False, max_colwidth=32))
        else:
            print(df.head(10).to_string(index=False, max_colwidth=32))
            print(f"    ... ({len(df)} rows total, full output saved)")
        print()

    print(f"{len(files) - len(failures)}/{len(files)} queries succeeded "
          f"-> outputs in {outdir}/")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
