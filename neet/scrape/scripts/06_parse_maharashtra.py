#!/usr/bin/env python3
"""
Maharashtra NEET-UG (MH-CET Cell) 2025 CAP Round-3 parser -> closing-rank cutoffs.

The PDF is a space-aligned text report (NOT a ruled table, so pdfplumber's
table extraction finds nothing — we parse text lines with a regex instead).
Each data line is one allotted candidate:

  Sr  AIR  NEETRoll  FormNo  Name...  G  Cat [subflags...]  CODE:College(status)

  1 629 3110416106 256021396 SARTHAK SATISH VALEKAR M OPEN 1103:GSMC MUMBAI(Ret.)
  6 1115 3110201398 256029299 REYA MEHENDALE F D1 DEF1 W 1103:GSMC MUMBAI(No Pref)
  8 1127 3110116136 256023054 HAZEL PUNMIYA F OPEN (W) 1103:GSMC MUMBAI(No Pref)

Anchors used to parse the variable-width line:
  - leading  "<Sr> <AIR> <10-digit roll> <form>"  (AIR = NEET All India Rank)
  - Gender token  M|F  separates the Name from the Category
  - college token "<3-4 digits>:<name>(<status>)" ends the line; everything
    between Gender and the college token is Category + optional sub-flags.

Rows with no college (e.g. "... Disqualified-Allotted by MCC") are skipped.
Cutoff = MAX AIR per (college, category). rank_space = 'NEET AIR'.
"""
from __future__ import annotations
import argparse, csv, re, warnings
from collections import Counter
from pathlib import Path
import pdfplumber

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "source" / "maharashtra.pdf"
DEFAULT_OUT = ROOT / "extracted_data" / "neet_maharashtra_2025_r3_cutoffs.csv"

# A data line: Sr AIR Roll(10) Form ... then the rest.
LINE_RE = re.compile(r"^(\d+)\s+(\d+)\s+(\d{10})\s+(\d+)\s+(.*)$")
# The allotted college is 'NNNN:College Name[(status)]' running to end of line.
# The trailing status (Ret.)/(No Pref) is OPTIONAL and sometimes wraps mid-token
# ("...(No"), so we grab from the code to end-of-line and strip any trailing
# parenthetical (or dangling "(word") afterwards. Requiring the '()' here was a
# bug that silently dropped ~75% of rows.
COLLEGE_RE = re.compile(r"(\d{3,4}):(.+)$")
STATUS_TAIL_RE = re.compile(r"\s*\([^()]*\)?\s*$")  # trailing (status) or dangling "(No"
# Gender token that separates Name from Category.
GENDER_RE = re.compile(r"\b([MF])\b")


def parse(src: Path):
    buckets = {}          # (college_code, college_name, category) -> max AIR
    n = skip_nocollege = skip_other = 0
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for raw in (page.extract_text() or "").split("\n"):
                line = raw.strip()
                m = LINE_RE.match(line)
                if not m:
                    continue
                air = int(m.group(2))
                rest = m.group(5)  # "Name... G Cat [flags] CODE:College(status)"

                col = COLLEGE_RE.search(rest)
                if not col:
                    # e.g. "Disqualified-Allotted by MCC" — no state seat
                    skip_nocollege += 1
                    continue
                code = col.group(1)
                # strip the trailing (status)/(No... off the college name
                cname = STATUS_TAIL_RE.sub("", col.group(2)).strip()
                pre = rest[: col.start()].strip()  # "Name... G Cat [flags]"

                # split Name from Category at the LAST standalone gender token
                gmatches = list(GENDER_RE.finditer(pre))
                if not gmatches:
                    skip_other += 1
                    continue
                g = gmatches[-1]
                after_gender = pre[g.end():].strip()  # "Cat [subflags]"
                if not after_gender:
                    skip_other += 1
                    continue
                # Category = first token; the rest are sub-quota flags (W/DEF1/EMR..)
                category = after_gender.split()[0]

                n += 1
                key = (code, cname, category)
                if air > buckets.get(key, 0):
                    buckets[key] = air
    return buckets, n, skip_nocollege, skip_other


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    buckets, n, skip_nc, skip_o = parse(args.src)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Institute", "Institute Code", "Category",
                    "Academic Program Name", "Seat Type", "Round",
                    "Closing Rank", "rank_space"])
        for (code, cname, cat), air in sorted(buckets.items(), key=lambda x: x[1]):
            # MH R3 file is MBBS/BDS combined; program not distinguished per row here.
            w.writerow([cname, code, cat, "MBBS/BDS", "State Quota", "R3",
                        air, "NEET AIR"])
    print(f"wrote {args.out}: {len(buckets)} buckets from {n} rows "
          f"(skipped: {skip_nc} no-college, {skip_o} unparsed)")
    print("  colleges:", len({(c, nm) for c, nm, _ in buckets}))
    print("  categories:", dict(Counter(k[2] for k in buckets)))


if __name__ == "__main__":
    main()
