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

# Maharashtra's ALLOTTED seat category is the last category-like token in the
# segment between gender and the college. It carries the base category plus
# optional prefixes/suffix we decompose into flags:
#   H  prefix  -> Home-University seat   (HOPEN, HOBC, HEWS ...)
#   EM prefix  -> EWS-Minority sub-pool  (EMOBC, EMSEBC, EMNTD ...)
#   W  suffix / trailing (W) or bare 'W' -> female-reserved seat
# We match the base against a known vocabulary so junk tokens (HA/PEM/DEF flags,
# stray words) don't get mistaken for a category.
BASE_CATEGORIES = {
    "OPEN", "OBC", "SEBC", "EWS", "SC", "ST",
    "NTB", "NTC", "NTD", "VJA", "MINO", "MKB",
    "DEF1", "DEF2", "DEF3", "I.Q.", "ORPHAN", "ORPHANC",
}

# The MH R3 file does not label MBBS vs BDS per row, but the college name does
# (Amogh's heuristic): a Medical college -> MBBS, a Dental college -> BDS.
# MH fuses M/D into acronyms (GMC/GSMC/BJMC/IGMC/PMC = medical; GDC = dental), so
# we match those acronym suffixes plus the spelled-out words. A name hitting both
# (or neither) is flagged "REVIEW" for manual check rather than guessed.
_MED_RE = re.compile(r"MEDICAL|\bMED\b|[A-Z]MC\b|\bMC\b|IMS|\bMH\b")
_DEN_RE = re.compile(r"DENTAL|[A-Z]DC\b|\bDC\b")


def program_from_name(name: str) -> str:
    u = name.upper()
    med = bool(_MED_RE.search(u))
    den = bool(_DEN_RE.search(u))
    if med and den:
        return "REVIEW"   # ambiguous — manual review
    if med:
        return "MBBS"
    if den:
        return "BDS"
    return "REVIEW"       # neither — manual review


def classify_category(seg: str):
    """From the category segment, return (base_category, is_female, is_home_univ,
    is_em) or None if no known category token is found."""
    is_female = ("(W)" in seg) or bool(re.search(r"\bW\b", seg))
    # remove parentheticals and standalone W, then scan tokens right-to-left for
    # the first one that resolves to a known base category.
    s = re.sub(r"\([^)]*\)", " ", seg)
    s = re.sub(r"\bW\b", " ", s)
    for tok in reversed(s.split()):
        t = tok.strip().upper().lstrip("-")
        is_em = t.startswith("EM")
        core = t[2:] if is_em else t
        is_home = core.startswith("H") and core[1:] in BASE_CATEGORIES
        base = core[1:] if is_home else core
        # a trailing W got stripped above, but EMOBCW-style tokens keep W in-core
        if base.endswith("W") and base[:-1] in BASE_CATEGORIES:
            base = base[:-1]
            is_female = True
        if base in BASE_CATEGORIES:
            return base, is_female, is_home, is_em
    return None


def parse(src: Path):
    # key -> max AIR, where key = (code, name, base_cat, female, home, em)
    buckets = {}
    n = skip_nocollege = skip_other = skip_nocat = 0
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
                    # e.g. "Choice Not Available" / "Disqualified" — no seat
                    skip_nocollege += 1
                    continue
                code = col.group(1)
                cname = STATUS_TAIL_RE.sub("", col.group(2)).strip()
                pre = rest[: col.start()].strip()  # "Name... G Cat [flags]"

                gmatches = list(GENDER_RE.finditer(pre))
                if not gmatches:
                    skip_other += 1
                    continue
                after_gender = pre[gmatches[-1].end():].strip()
                if not after_gender:
                    skip_other += 1
                    continue

                cls = classify_category(after_gender)
                if cls is None:
                    # no recognised category token — report, don't silently keep
                    skip_nocat += 1
                    continue
                base, female, home, em = cls

                n += 1
                key = (code, cname, base, female, home, em)
                if air > buckets.get(key, 0):
                    buckets[key] = air
    return buckets, n, skip_nocollege, skip_other, skip_nocat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    buckets, n, skip_nc, skip_o, skip_nocat = parse(args.src)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Institute", "Institute Code", "Category", "Is Female Seat",
                    "Is Home University", "Is EWS Minority",
                    "Academic Program Name", "Seat Type", "Round",
                    "Closing Rank", "rank_space"])
        review = set()
        for (code, cname, base, female, home, em), air in sorted(
            buckets.items(), key=lambda x: x[1]
        ):
            program = program_from_name(cname)
            if program == "REVIEW":
                review.add(cname)
            w.writerow([cname, code, base, "Yes" if female else "No",
                        "Yes" if home else "No", "Yes" if em else "No",
                        program, "State Quota", "R3", air, "NEET AIR"])

    # miss rate: rows with a college but no recognisable category (the floor)
    allotted = n + skip_nocat
    miss_pct = 100 * skip_nocat / allotted if allotted else 0
    print(f"wrote {args.out}: {len(buckets)} buckets from {n} allotted rows")
    print(f"  skipped: {skip_nc} no-college (Choice Not Available/DQ), "
          f"{skip_o} no-gender, {skip_nocat} no-recognised-category")
    print(f"  category miss rate (of rows WITH a college): "
          f"{skip_nocat}/{allotted} = {miss_pct:.2f}%")
    print("  colleges:", len({(c, nm) for c, nm, *_ in buckets}))
    print("  base categories:", dict(Counter(k[2] for k in buckets)))
    print("  female-seat buckets:", sum(1 for k in buckets if k[3]))
    if review:
        print(f"  ⚠ program REVIEW (name matched both/neither MC/DC) — {len(review)} colleges:")
        for nm in sorted(review):
            print(f"      {nm}")
    else:
        print("  program (MBBS/BDS from college name): 0 colleges need review")


if __name__ == "__main__":
    main()
