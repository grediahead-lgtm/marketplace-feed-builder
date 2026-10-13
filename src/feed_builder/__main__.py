import argparse
import os
import sys

from .core import build, read_table, to_sheets
from .xlsx import write_xlsx

REQUIRED = ["sku", "price"]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="feed_builder", description="Product table (CSV) -> Prom.ua import file (XLSX) + report")
    ap.add_argument("table")
    ap.add_argument("--out", default="out")
    ap.add_argument("--currency", default="UAH")
    ap.add_argument("--no-copy", action="store_true", help="do not copy Ukrainian name/description into the Russian fields")
    ap.add_argument("--strict", action="store_true", help="exit with code 2 if any row has an error")
    a = ap.parse_args(argv)
    with open(a.table, encoding="utf-8", newline="") as f:
        head, rows = read_table(f.read())
    low = [h.lower() for h in head]
    miss = [c for c in REQUIRED if c not in low]
    if miss or not ("name_uk" in low or "name_ru" in low):
        raise SystemExit("missing columns: %s (found: %s)" % (", ".join(miss + ([] if "name_uk" in low or "name_ru" in low else ["name_uk or name_ru"])), ", ".join(head)))
    products, groups, problems = build(rows, a.currency, not a.no_copy)
    os.makedirs(a.out, exist_ok=True)
    write_xlsx(os.path.join(a.out, "prom-import.xlsx"), to_sheets(products, groups))
    errs = [p for p in problems if p[1] == "error"]
    with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("# Report\n\nRows read: %d, exported: %d, skipped because of errors: %d, groups: %d\n\n" % (len(rows), len(products), len(rows) - len(products), len(groups)))
        f.write("Line numbers are lines of the input file (the header is line 1).\n\n")
        for line, level, msg in sorted(problems):
            f.write("- line %d [%s] %s\n" % (line, level, msg))
        if not problems:
            f.write("No problems found.\n")
    print("rows %d, exported %d, errors %d, warnings %d -> %s" % (len(rows), len(products), len(errs), len(problems) - len(errs), a.out))
    return 2 if (a.strict and errs) else 0


if __name__ == "__main__":
    sys.exit(main())
