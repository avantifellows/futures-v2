"""
Parse KCET 2025 Third Round cutoff PDFs into a tall CSV.

KEA changed the PDF format for 2025: cutoffs are now wide tables (one row per
college × course, one column per category code). This script uses pdfplumber
table extraction (which correctly handles multiline cell text) and unpivots
the wide format into a tall (tidy) CSV with one row per
(college, course, category, closing_rank).

Source PDFs (download to source/KA/engineering/ before running):
  KA_engg_2025_GEN_R3.pdf  — Seat Type: Rest of Karnataka (General quota)
  KA_engg_2025_HK_R3.pdf   — Seat Type: 371(j) Kalyana Karnataka (HK quota)

URLs:
  https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/PROF_CODE_E_R_11092025english.pdf
  https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/PROF_CODE_E_H_11092025english.pdf

Output:
  extracted_data/KA_engg_2025_all_cutoffs_R3.csv

Columns:
  college_code      — KEA college code (e.g. E001)
  college_name      — full name as in PDF
  course_name       — normalised course name (whitespace collapsed)
  domicile_pool     — GEN (Rest of KA) or HK (Kalyana Karnataka 371j)
  category_code     — e.g. GM, 1G, 2AG, SCH, STH …
  closing_rank      — numeric cutoff rank (NULL if seat not allotted)
  year              — 2025
  round             — 3  (Third Round)

Category code key (GEN pool):
  Vertical prefix: 1=Cat1, 2A=Cat2A, 2B=Cat2B, 3A=Cat3A, 3B=Cat3B,
                   GM=General Merit, SC=Scheduled Caste, ST=Scheduled Tribe,
                   NRI, OPN=Open, OTH=Other
  Horizontal suffix: G=General, K=Kannada Medium, R=Rural, P=PWD
  HK pool adds H suffix: 1H, 2AH, GMH, SCH …

Usage:
  python3 scripts/parse_KA_2025.py            # parse + write CSV
  python3 scripts/parse_KA_2025.py --dry-run  # stats only, no write
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT_DIR = ROOT / "extracted_data"

GEN_PDF = ROOT / "source" / "KA" / "engineering" / "KA_engg_2025_GEN_R3.pdf"
HK_PDF  = ROOT / "source" / "KA" / "engineering" / "KA_engg_2025_HK_R3.pdf"
OUT_CSV = OUT_DIR / "KA_engg_2025_all_cutoffs_R3.csv"

YEAR  = 2025
ROUND = 3

CATS_GEN = [
    "1G","1K","1R",
    "2AG","2AK","2AR",
    "2BG","2BK","2BR",
    "3AG","3AK","3AR",
    "3BG","3BK","3BR",
    "GM","GMK","GMP","GMR",
    "NRI","OPN","OTH",
    "SCG","SCK","SCR",
    "STG","STK","STR",
]
CATS_HK = [
    "1H","1KH","1RH",
    "2AH","2AKH","2ARH",
    "2BH","2BKH","2BRH",
    "3AH","3AKH","3ARH",
    "3BH","3BKH","3BRH",
    "GMH","GMKH","GMPH","GMRH",
    "SCH","SCKH","SCRH",
    "STH","STKH","STRH",
]

COLLEGE_RE = re.compile(r"College:\s*(E\d+)\s+(.*)")


# Word fragments that appear at end-of-line in this PDF due to narrow columns.
# Each tuple: (broken_end, broken_start) — join without space when seen.
_WORD_BREAKS = [
    ("COMMUNICATIO", "N"),
    ("INSTRUMENTATI", "ON"),
    ("INSTRUMENTATIO", "N"),
    ("TELECOMMUNIC", "ATION"),
    ("TELECOMMUNICA", "TION"),
    ("ENVIRONMETA", "L"),    # ENVIRONMENTAL
    ("ENVIRONMENTA", "L"),
    ("BIOTECHNOLOG", "Y"),
    ("Clou","d"),             # CLOUD
    ("INTERNE", "T"),        # INTERNET
    ("MANUFACTURIN", "G"),
    ("SUSTAINABILIT", "Y"),
    ("ARTIFICIA", "L"),      # ARTIFICIAL
    ("INTEGTATE", "D"),      # INTEGRATED (source typo)
    ("INTEGTATED", ""),      # already full but is a typo — keep as is
]
_WORD_BREAK_LOOKUP = {end: start for end, start in _WORD_BREAKS}

# A line ending in "(" plus a SINGLE bare letter (e.g. "ENGINEERING(A",
# "ENGG(I") is the start of a parenthetical word cut off by column width --
# no single letter is a standalone abbreviation in this data, so it must be
# a fragment. Deliberately NOT extended to all 2-3 letter runs: those are
# often already-complete abbreviations followed by a new word, e.g. "(IOT"
# then "INCLUDING BLOCK CHAIN)" or "(BIG" then "DATA)" -- gluing those
# without a space would wrongly produce "IOTINCLUDING"/"BIGDATA".
_PAREN_FRAGMENT_RE = re.compile(r"\([A-Za-z]?$")

# Specific 2-3 letter "(" + fragment endings, individually confirmed against
# the source PDF to always be mid-word continuations, never a complete
# abbreviation followed by a new word (unlike "(IOT"/"(BIG" above).
_PAREN_KNOWN_FRAGMENTS = ("(DA", "(AR", "(BL", "(CY", "(DE", "(SO", "(VLS")

def _clean_cell(v: str | None) -> str:
    """Collapse newlines in a PDF cell value, repairing known mid-word breaks."""
    if v is None:
        return ""
    parts = str(v).split("\n")
    result = parts[0]
    for part in parts[1:]:
        stripped_result = result.rstrip()

        if stripped_result.endswith("-"):
            # Hyphenated word wrap (e.g. "BIO-" / "TECHNOLOGY") -- the hyphen
            # belongs to the word itself, so glue with no space and keep it.
            result = stripped_result + part
            continue

        if part.startswith(")"):
            # A wrapped closing paren never has a space before it.
            result = stripped_result + part
            continue

        if _PAREN_FRAGMENT_RE.search(stripped_result) or stripped_result.endswith(_PAREN_KNOWN_FRAGMENTS):
            result = stripped_result + part
            continue

        # Look for a known broken fragment as a SUFFIX of the text so far,
        # not just as the whole last whitespace-token: punctuation like "("
        # is often glued directly onto the preceding word with no space
        # (e.g. "...ENGG(ARTIFICIA"), which would otherwise hide the match.
        matched_frag = next(
            (frag for frag in _WORD_BREAK_LOOKUP if stripped_result.endswith(frag)),
            None,
        )
        expected_suffix = _WORD_BREAK_LOOKUP.get(matched_frag) if matched_frag else None
        if expected_suffix is not None and (part == expected_suffix or part.startswith(expected_suffix + " ")):
            result = stripped_result + part  # glue without space
        else:
            result = stripped_result + " " + part
    # A space is never legitimate right before a closing paren, whether it
    # came from a line-join above or was already in the source PDF text
    # (e.g. "DESIGN )" appears as literal text on a single line).
    return re.sub(r"\s+\)", ")", " ".join(result.split()))

def _parse_rank(v: str) -> float | None:
    s = _clean_cell(v)
    if s in ("--", "-", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None

def _course_key(name: str) -> str:
    """Strip whitespace/punctuation so differently-split PDF fragments compare equal."""
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def canonicalize_course_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse course_name variants that are the same course but got split at
    different mid-word points by pdfplumber (e.g. "...(D ATA SCIENCE)" vs
    "...(DA TA SCIENCE)"). _WORD_BREAKS only repairs specific known split
    points; this catches the rest by grouping names that are identical once
    whitespace/punctuation is removed, and keeping whichever spelling is used
    by the most distinct colleges as the canonical one.
    """
    college_counts = df.groupby("course_name")["college_code"].nunique()

    canonical: dict[str, tuple[str, int]] = {}
    for name, n_colleges in college_counts.items():
        key = _course_key(name)
        if key not in canonical or n_colleges > canonical[key][1]:
            canonical[key] = (name, n_colleges)

    mapping = {name: canonical[_course_key(name)][0] for name in college_counts.index}
    changed = {name: canon for name, canon in mapping.items() if name != canon}
    if changed:
        print(f"\nCollapsed {len(changed)} course_name variant(s) into canonical spellings:")
        for name, canon in sorted(changed.items()):
            print(f"  {name!r} -> {canon!r}")

    df["course_name"] = df["course_name"].map(mapping)
    return df


# Administrative degree-title prefixes that don't change WHICH program a row
# is -- e.g. "B TECH IN COMPUTER ENGINEERING" vs "COMPUTER ENGINEERING" is the
# same course, just some colleges spell out the full B.Tech title in the PDF
# and others don't. Deliberately excludes "(HONS)" variants: Honours may be a
# genuinely distinct track with its own seats/cutoffs, not pure formatting.
_DEGREE_PREFIX_RE = re.compile(r"^(B\.?\s*TECH\s+IN\s+|BTECH\s+IN\s+)", re.IGNORECASE)


def _normalize_course_name(name: str) -> str:
    """
    Formatting-only normalization for grouping the same program across
    colleges: strips administrative degree prefixes, unifies ENGG/ENGINEERING
    and parenthesis spacing, and standardizes case. Never touches the actual
    subject/specialization wording, so it won't merge two different programs
    (e.g. "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING" and "COMPUTER
    SCIENCE AND ENGINEERING (AIML)" stay separate -- they may be distinct
    AICTE-approved branches with different real cutoffs, not just spelling).
    """
    n = _DEGREE_PREFIX_RE.sub("", name.strip())
    n = re.sub(r"\bENGG\b", "ENGINEERING", n, flags=re.IGNORECASE)
    n = re.sub(r"\s*\(\s*", "(", n)
    n = re.sub(r"\s*\)\s*", ")", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n.upper()


def apply_canonical_course_name(df: pd.DataFrame) -> pd.DataFrame:
    """Overwrite course_name with its formatting-only canonical form (see _normalize_course_name)."""
    names = df["course_name"].unique()
    mapping = {name: _normalize_course_name(name) for name in names}

    groups: dict[str, list[str]] = {}
    for name, canon in mapping.items():
        groups.setdefault(canon, []).append(name)
    merged = {canon: variants for canon, variants in groups.items() if len(variants) > 1}
    if merged:
        total = sum(len(v) for v in merged.values())
        print(f"\nNormalized {total} course_name variant(s) into {len(merged)} canonical name(s):")
        for canon, variants in sorted(merged.items()):
            print(f"  {canon!r} <- {sorted(variants)}")

    df["course_name"] = df["course_name"].map(mapping)
    return df

def parse_pdf(path: Path, cats: list[str], domicile: str) -> list[dict]:
    """
    Extract all tables from the PDF, match each to its college header,
    unpivot category columns into rows, keep only non-null ranks.
    """
    rows: list[dict] = []

    current_college: tuple[str | None, str | None] = (None, None)

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            # Get college headers from the page text
            text = page.extract_text() or ""
            college_headers: list[tuple[str, str]] = []
            for line in text.split("\n"):
                m = COLLEGE_RE.match(line.strip())
                if m:
                    college_headers.append((m.group(1).strip(), m.group(2).strip()))

            tables = page.extract_tables()

            # Consume headers in order as real tables are found on this page.
            # A table found before its header shows up (or with no header left
            # to consume on this page) inherits current_college from a prior page.
            header_idx = 0
            for i, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue

                if header_idx < len(college_headers):
                    current_college = college_headers[header_idx]
                    header_idx += 1

                college_code, college_name = current_college

                header_row = table[0]
                # Validate category columns match expected
                actual_cats = [_clean_cell(c) for c in header_row[1:]]
                if actual_cats != cats:
                    # Tolerate minor mismatches but warn
                    print(
                        f"  WARNING p{page.page_number} table {i}: "
                        f"expected {len(cats)} cats, got {len(actual_cats)}"
                    )

                for data_row in table[1:]:
                    if not data_row or data_row[0] is None:
                        continue
                    course_name = _clean_cell(data_row[0])
                    if not course_name or course_name == "Course Name":
                        continue

                    for j, cat in enumerate(cats, start=1):
                        rank = _parse_rank(data_row[j] if j < len(data_row) else None)
                        if rank is not None:
                            rows.append({
                                "college_code": college_code,
                                "college_name": college_name,
                                "course_name": course_name,
                                "domicile_pool": domicile,
                                "category_code": cat,
                                "closing_rank": rank,
                                "year": YEAR,
                                "round": ROUND,
                            })

    return rows


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and print stats; don't write CSV.")
    args = ap.parse_args()

    for path in (GEN_PDF, HK_PDF):
        if not path.exists():
            sys.exit(f"Missing PDF: {path}")

    print("Parsing GEN (Rest of Karnataka)...")
    gen_rows = parse_pdf(GEN_PDF, CATS_GEN, "GEN")
    print(f"  {len(gen_rows):,} non-null category-rank rows")

    print("Parsing HK (Kalyana Karnataka 371j)...")
    hk_rows = parse_pdf(HK_PDF, CATS_HK, "HK")
    print(f"  {len(hk_rows):,} non-null category-rank rows")

    df = pd.DataFrame(gen_rows + hk_rows)
    df["closing_rank"] = pd.to_numeric(df["closing_rank"], errors="coerce")
    df["year"] = df["year"].astype("Int64")
    df["round"] = df["round"].astype("Int64")
    df = canonicalize_course_names(df)
    df = apply_canonical_course_name(df)

    print(f"\nTotal rows     : {len(df):,}")
    print(f"Colleges       : {df['college_code'].nunique()}")
    print(f"Courses        : {df['course_name'].nunique()}")
    print(f"Category codes : {df['category_code'].nunique()}")
    print(f"Domicile pools : {sorted(df['domicile_pool'].unique())}")

    print("\nSample rows (UVCE):")
    sample = df[df["college_code"] == "E001"].head(10)
    print(sample[["college_code","course_name","domicile_pool","category_code","closing_rank"]].to_string(index=False))

    print("\nDistinct course names:")
    for c in sorted(df["course_name"].unique()):
        print(f"  {c}")

    if args.dry_run:
        print("\n[dry-run] No file written.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nWritten: {OUT_CSV}  ({len(df):,} rows)")


if __name__ == "__main__":
    main()
