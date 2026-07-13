#!/usr/bin/env python3
"""
Telangana NEET-UG (KNRUHS) 2025 mop-up allotment parser -> closing-rank cutoffs.

Space-aligned TEXT report (no ruled table). Structure:

  COLL :: OMCH - OSMANIA MEDICAL COLLEGE, HYDERABAD   <- section header (college)
  CRS  :: MBBS - ...                                  <- course
  RANK ROLL_NO STUDENT_NAME CAT SX ... <ALLOT-CODE>    <- one row per candidate
  4846 4201306421 BOGGARAPU ... OC M OPEN-GEN-P1

We carry the current college forward from each "COLL ::" header. RANK is the NEET
All India Rank. The trailing ALLOT-CODE encodes the SEAT:
  <category>-<GEN|FEM>-[MSM-]P<phase>
    category : OPEN / BCA..BCE / SC / SC2 / SC3 / ST / MIN ...
    GEN|FEM  : general vs female-reserved seat  (the (W) equivalent)
    MSM      : Muslim-minority sub-pool
    P1/P2/P3 : counselling phase

Cutoff = MAX AIR per (college, category, is_female). rank_space = 'NEET AIR'.
"""
from __future__ import annotations
import argparse, csv, re, warnings
from collections import Counter
from pathlib import Path
import pdfplumber

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "source" / "telangana.pdf"
DEFAULT_OUT = ROOT / "extracted_data" / "neet_telangana_2025_cutoffs.csv"

COLL_RE = re.compile(r"COLL\s*::\s*(\S+)\s*-\s*(.+)$")
DATA_RE = re.compile(r"^(\d+)\s+(\d{10})\s+(.*)$")
# trailing allotment code: CATEGORY-(GEN|FEM)[-<sub-pools>...]-P<n>
# The sub-pool segments between GEN/FEM and the phase vary (MSM, CAP, MRC, ...);
# we only need the leading category and the GEN/FEM split, so allow any middle.
ALLOT_RE = re.compile(r"([A-Z0-9]+)-(GEN|FEM)(?:-[A-Z]+)*-P(\d+)\s*$")


def parse(src: Path):
    buckets = {}          # (code, name, category, is_female) -> max AIR
    current = None        # (code, name)
    n = skip = 0
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for raw in (page.extract_text() or "").split("\n"):
                line = raw.strip()
                cm = COLL_RE.search(line)
                if cm:
                    current = (cm.group(1).strip(), cm.group(2).strip())
                    continue
                dm = DATA_RE.match(line)
                if not dm:
                    continue
                air = int(dm.group(1))
                am = ALLOT_RE.search(dm.group(3))
                if not am or not current:
                    skip += 1
                    continue
                category = am.group(1)                 # OPEN / BCB / SC2 / ST / MIN
                is_female = am.group(2) == "FEM"
                code, name = current
                key = (code, name, category, is_female)
                if air > buckets.get(key, 0):
                    buckets[key] = air
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
        w.writerow(["Institute", "Institute Code", "Category", "Is Female Seat",
                    "Academic Program Name", "Seat Type", "Round",
                    "Closing Rank", "rank_space"])
        for (code, name, cat, female), air in sorted(buckets.items(), key=lambda x: x[1]):
            w.writerow([name, code, cat, "Yes" if female else "No",
                        "MBBS", "State Quota", "MopUp", air, "NEET AIR"])
    print(f"wrote {args.out}: {len(buckets)} buckets ({skip} rows skipped)")
    print("  colleges:", len({(c, nm) for c, nm, *_ in buckets}))
    print("  categories:", dict(Counter(k[2] for k in buckets)))
    print("  female-seat buckets:", sum(1 for k in buckets if k[3]))


if __name__ == "__main__":
    main()
