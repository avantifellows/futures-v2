#!/usr/bin/env python3
"""
Andhra Pradesh NEET-UG (Dr NTR UHS) 2025 R3 parser -> closing-rank cutoffs.

Layout: the college name is a SECTION-HEADER row (all other cells '-'), followed
by that college's student rows. Header may not repeat on continuation pages, so
we carry forward the last-seen college.

Student row (10 cols):
  S.No | NEET RANK(AIR) | Roll | Score | Name | Gender | Category | Local Area
       | Allotment Details | Phase

The SEAT category is inside 'Allotment Details', NOT the col-6 'Category' (which
is the student's own social category). Allotment Details =
  '<collegeAbbr> - MBBS - <region:AU/SVU/APUR> - <allottedCategory> - <sub> --- <opt>'
so token[3] after splitting the head on ' - ' is the allotted category.

Cutoff = MAX AIR per (college, allotted category, program). AP taxonomy:
OC / BCA-E / SC1-3 / ST / EWS / MINORITY. rank_space = 'NEET AIR'.
"""
from __future__ import annotations
import argparse, csv, warnings
from collections import Counter
from pathlib import Path
import pdfplumber

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "source" / "andhra.pdf"
DEFAULT_OUT = ROOT / "extracted_data" / "neet_andhra_2025_r3_cutoffs.csv"

# Header/junk rows we must not treat as a college name.
_NOT_COLLEGE = {"S.No.", "S.No"}


def clean(s):
    return (s or "").replace("\n", " ").strip()


def parse_allotment(ad):
    """Return (program, allotted_category) from the compound string, or (None,None)."""
    head = ad.split("---")[0].strip()
    toks = [x.strip() for x in head.split(" - ")]
    if len(toks) < 4:
        return None, None
    program = toks[1].upper()
    program = "BDS" if program.startswith("BDS") else "MBBS" if "MBBS" in program else program
    return program, toks[3]


def parse(src: Path):
    buckets, n, skip = {}, 0, 0
    current_college = None
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables() or []:
                for r in t:
                    c0 = clean(r[0])
                    # section-header row: first cell is a name, rest are '-'/empty
                    rest = [clean(x) for x in r[1:]]
                    if c0 and c0 not in _NOT_COLLEGE and all(x in ("", "-") for x in rest):
                        current_college = c0
                        continue
                    if not c0.isdigit() or len(r) < 9:
                        continue
                    air = clean(r[1]).replace(",", "")
                    ad = clean(r[8])
                    if not air.isdigit() or not current_college or not ad or ad == "-":
                        skip += 1
                        continue
                    program, cat = parse_allotment(ad)
                    if not program or not cat:
                        skip += 1
                        continue
                    n += 1
                    key = (current_college, cat, program)
                    buckets[key] = max(buckets.get(key, 0), int(air))
    return buckets, n, skip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    buckets, n, skip = parse(args.src)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Institute", "Category", "Academic Program Name",
                    "Seat Type", "Round", "Closing Rank", "rank_space"])
        for (college, cat, program), air in sorted(buckets.items(), key=lambda x: x[1]):
            w.writerow([college, cat, program, "State Quota", "R3", air, "NEET AIR"])
    print(f"wrote {args.out}: {len(buckets)} buckets from {n} rows ({skip} skipped)")
    print("  colleges:", len({k[0] for k in buckets}),
          "| categories:", dict(Counter(k[1] for k in buckets)))


if __name__ == "__main__":
    main()
