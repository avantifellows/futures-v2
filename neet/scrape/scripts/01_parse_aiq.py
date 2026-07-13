#!/usr/bin/env python3
"""
AIQ (All India Quota / MCC) NEET-UG 2025 cutoffs — CORRECT version.

Unions two MCC files to get complete, category-labelled closing ranks:

  R1 result (aiq_r1.pdf, flat 8-col): EVERY allotted student with category.
    SNo | AIR | Quota | Institute | Course | AllottedCategory | CandCat | Status
    -> the complete baseline. (The R3-only parser missed 19k students who kept
       their R1 seat, because R3 leaves their category blank.)

  R3 result (aiq.pdf, journey ledger): the R2/R3 fresh-allotments & upgrades,
    which DO carry category in the R3 block. These push closing ranks to their
    final (looser) values as seats free up across rounds.

Closing rank per (institute, category, course) = MAX AIR across the union.
rank_space = 'NEET AIR' (national).
"""
from __future__ import annotations
import csv, sys, warnings
from collections import defaultdict
import pdfplumber

warnings.filterwarnings("ignore")
R1 = sys.argv[1] if len(sys.argv) > 1 else "aiq_r1.pdf"
R3 = sys.argv[2] if len(sys.argv) > 2 else "aiq.pdf"
OUT = sys.argv[3] if len(sys.argv) > 3 else "neet_aiq_2025_cutoffs.csv"

COURSES = {"MBBS", "BDS", "B.SC. NURSING", "BSC NURSING", "B.SC NURSING"}
CATEGORIES = {"Open", "OBC", "EWS", "SC", "ST",
              "Open PwD", "OBC PwD", "EWS PwD", "SC PwD", "ST PwD"}


def clean(s):
    return (s or "").replace("\n", " ").strip()


def norm_course(s):
    s = clean(s).upper()
    if s.startswith("B.SC") or "NURSING" in s:
        return "BSc Nursing"
    return "BDS" if s.startswith("BDS") else "MBBS"


def parse_r1(path, buckets):
    """Flat 8-col: [SNo, AIR, Quota, Institute, Course, AllotCat, CandCat, Status]."""
    n = skip = 0
    with pdfplumber.open(path) as pdf:
        for pi in range(2, len(pdf.pages)):  # skip legend pages 0-1
            for t in pdf.pages[pi].extract_tables() or []:
                for r in t:
                    if not r or not str(r[0]).strip().isdigit() or len(r) < 8:
                        continue
                    air = clean(r[1]).replace(",", "")
                    inst = clean(r[3])
                    course = norm_course(r[4])
                    cat = clean(r[5])
                    if not air.isdigit() or not inst or cat not in CATEGORIES:
                        skip += 1
                        continue
                    n += 1
                    key = (inst, cat, course)
                    air = int(air)
                    if air > buckets[key]:
                        buckets[key] = air
    return n, skip


def parse_r3_movements(path, buckets):
    """R3 journey ledger: capture only rows with a populated R3 block (fresh/upgrade),
    which carry AllottedCategory. Layout ~16-17 cols; locate the R3 institute+course+cat
    semantically (last course token; category = known-cat cell after it)."""
    n = skip = 0
    with pdfplumber.open(path) as pdf:
        for pi in range(2, len(pdf.pages)):
            for t in pdf.pages[pi].extract_tables() or []:
                for r in t:
                    if not r or not str(r[0]).strip().isdigit():
                        continue
                    air = str(r[0]).strip()
                    cells = [clean(c) for c in r]
                    course_idxs = [i for i, c in enumerate(cells) if c.upper() in COURSES]
                    if not course_idxs:
                        continue
                    ci = course_idxs[-1]  # final round's course
                    # a category cell must follow (only true for R2/R3 allotments)
                    cat = ""
                    for j in range(ci + 1, len(cells)):
                        if cells[j] in CATEGORIES:
                            cat = cells[j]
                            break
                    if not cat:
                        continue  # R1-stayer (no cat) — already covered by R1 file
                    inst = cells[ci - 1] if ci >= 1 else ""
                    if not inst:
                        skip += 1
                        continue
                    n += 1
                    key = (inst, cat, norm_course(cells[ci]))
                    a = int(air)
                    if a > buckets[key]:
                        buckets[key] = a
    return n, skip


def main():
    buckets = defaultdict(int)
    n1, s1 = parse_r1(R1, buckets)
    print(f"R1: {n1:,} rows used ({s1} skipped); buckets now {len(buckets):,}")
    before = len(buckets)
    n3, s3 = parse_r3_movements(R3, buckets)
    print(f"R3 movements: {n3:,} rows used; buckets now {len(buckets):,} (+{len(buckets)-before} new)")

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Institute", "Category", "Academic Program Name",
                    "Seat Type", "Round", "Closing Rank", "rank_space"])
        for (inst, cat, course), air in sorted(buckets.items(), key=lambda x: x[1]):
            w.writerow([inst, cat, course, "All India", "R1+R3", air, "NEET AIR"])
    print(f"wrote {OUT}: {len(buckets):,} buckets")

    # anchor: AIIMS New Delhi MBBS by category (must be present now)
    print("\nANCHOR AIIMS New Delhi MBBS:")
    for (inst, cat, course), air in sorted(buckets.items()):
        if "AIIMS" in inst.upper() and "NEW DELHI" in inst.upper() and course == "MBBS":
            print(f"  {cat:10} closing AIR = {air:,}")


if __name__ == "__main__":
    main()
