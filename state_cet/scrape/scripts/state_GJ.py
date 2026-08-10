"""
Gujarat ACPC — engineering + pharmacy closing-ranks pipeline.

Authority:  Admission Committee for Professional Courses (ACPC), Gujarat
Portal:     https://gujacpc.admissions.nic.in/eservices-be_b-tech/

Two streams, two independent source PDFs, same pipeline shape (parse ->
classify govt scope -> 5-cat consolidate, rank file + percentile file).

=====================================================================
ENGINEERING
=====================================================================
Source: "Last Admitted Rank in Online Round of First Year Degree
         Engineering A.Y. 2025-26" PDF (ACPC closure data) at
         cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/
           uploads/2026/06/202606121114968955.pdf

This is a BETTER/newer source than the earlier "Round-3 Last Admitted Rank"
PDF (still kept at source/GJ/engineering/GJ_ACPC_2025_R3_LastAdmittedRank.pdf
for reference, no longer used by this script):
  - It is ACPC's final CLOSURE data (PDF title metadata: "CLOSURE_BE_010426"),
    i.e. the true last-admitted cutoff for the year, not tied to a specific
    numbered round.
  - It carries BOTH the closing rank AND a closing percentile-equivalent
    composite score ("MARKS" in the raw header, but it is GUJCET's
    normalized 0-100 composite score, not raw exam marks — see below) per
    category, in one row per (institute, course).
  - The Home-State (H) columns are already a SINGLE merit rank per category
    — no more separate GUJCET-based vs JEE-based rows to reconcile, because
    Gujarat's Home-State merit list already blends GUJCET/JEE/Class-12 into
    one composite score per candidate (see rank_basis below).

PDF format (single wide tabular structure across 34 pages, 21 columns):
  INAME | INST_TYPE | CNAME |
  OP_H_RANK  | OP_H_MARKS  |
  SC_H_RANK  | SC_H_MARKS  |
  ST_H_RANK  | ST_H_MARKS  |
  SEBC_H_RANK| SEBC_H_MARKS|
  EWS_H_RANK | EWS_H_MARKS |
  ESM_H_RANK | ESM_H_MARKS |
  TFWS_H_RANK| TFWS_H_MARKS|
  OP_AI | JEE_AI_RANK | TFWS_AI | TF_JEE_AI_RANK

  "_H_" = Home State (Gujarat-domicile) quota — what this script extracts.
  "_AI" = All-India quota (JEE-only seats) — INTENTIONALLY LEFT OUT for now
          (per request); revisit if AI-quota cutoffs are needed later.

  Category codes: OP, SC, ST, SEBC, EWS, ESM (Ex-Servicemen, horizontal),
  TFWS (Tuition Fee Waiver Scheme, economic — separate sub-pool).

  College/course names wrap across PDF lines. Institute names wrap at word
  boundaries (simple "\\n" -> " " is safe, matching every other state
  script's convention here). Course names, unlike institute names, wrap by
  FORCED CHARACTER WIDTH and routinely break mid-word (e.g.
  "COMMUNICATIO\\nN ENGINEERING" -> "COMMUNICATION ENGINEERING",
  "ENVIRONMENTA\\nL ENGINEERING" -> "ENVIRONMENTAL ENGINEERING"). A plain
  space-join would leave stray internal spaces ("COMMUNICATIO N"), so course
  names go through `_join_wrapped_course_name()` instead — verified by hand
  against all 105 distinct course strings in the 2025-26 PDF.

Institute type taxonomy (INST_TYPE column) — DIFFERENT from the old R3 PDF's
taxonomy (GIA/GOVT/PVT/Self-Fin):
  GOV      = Government
  GIA      = Grant-in-Aid (state-aided autonomous)
  SFI      = Self-Financed (private)
  UNI-SFI  = Self-financed institute run under a university
  COE      = "Centre of Excellence" self-financed private university/institute
  PPP      = Public-Private-Partnership (1 college: GIDC Degree Engineering
             College — GIDC land, privately run/self-financed in practice)
  Auto     = Autonomous — only IITRAM (Institute of Infrastructure, Tech.,
             Research & Management), a state-legislature-established,
             fully state-funded autonomous technical institute. Treated as
             govt-scope (State-Univ-Dept bucket) even though it isn't
             literally a university department, because it is a standalone
             state-funded technical institution, closest existing bucket.

=====================================================================
PHARMACY
=====================================================================
Source: "Last Admitted Rank after completion of online Rounds : First Year
         Degree/Diploma Pharmacy" (Admission Year 2024-25) at
         acpc.gujarat.gov.in/assets/uploads/media-uploader/
           pharma-closure-2024-251746779890.pdf
(One year behind engineering — 2024-25 is the latest pharmacy closure PDF
ACPC has published as of this writing; re-check the portal for a 2025-26 one.)

PDF format (6 pages, 19 columns) — same shape as engineering, one row per
(institute, program):
  INAME | Program | Type |
  OPEN_HS | OPEN_MERITMARKS |
  SC_HS   | SC_MERIT MARKS  |
  ST_HS   | ST_MERIT MARKS  |
  SEBC_HS | SEBC_MERITMARKS |
  EWS_HS  | EWS_MERITMARKS  |
  ESM_HS  | ESM_MERIT MARKS |
  TFWS_HS | TFWS_MERIT MARKS|
  OPEN_AI | TFWS_AI

  Program: Bpharm (B.Pharm) or Dpharm (D.Pharm, diploma) — used as
  branch_name/branch_code (no separate course-name column like engineering).
  Type: GOVT / GIA / SFI only (no UNI-SFI/COE/PPP/Auto seen here).
  Category codes: OPEN (-> GEN, same slot as engineering's "OP"), SC, ST,
  SEBC, EWS, ESM, TFWS — identical semantics to engineering.

  Institute names wrap at word boundaries only (no mid-word breaks observed
  across all 119 distinct names) — plain "\\n" -> " " is safe, no special
  join function needed here.

  KNOWN PDF QUIRK — ESM_MERIT MARKS column: whenever ESM_HS (rank) is
  numeric, ESM_MERIT MARKS is *always* exactly equal to it (verified across
  every such row in the file) — never a genuine 0-100 percentile-style value
  like every other category shows. This is almost certainly a column-
  boundary extraction artifact from the two-line "ESM_MERIT\\nMARKS" header
  shifting the bounding box onto the adjacent rank cell, not a real
  percentile. `parse_gj_pharmacy_pdf()` nulls it out rather than passing
  along a fabricated-looking number. ESM never lands in the 5-cat canonical
  files anyway (it's a horizontal sub_pool, not one of the 5 verticals), so
  this only affects the raw/govt-scope long files.

  Gujarat pharmacy admission (unlike engineering) is NOT GUJCET-based — GUJCET
  is a PCM engineering test. ACPC has no separate pharmacy CET; admission is
  by ACPC's Home-State merit list. The PDF doesn't state the exact merit
  formula, so `PHARM_RANK_BASIS`/`PHARM_PERCENTILE_BASIS` describe it as
  "ACPC merit rank" without claiming a specific composite formula — don't
  assume it's the same 1/3+1/3+1/3 formula as engineering.

For canonical 5-cat mapping (NCST schema), both streams:
  OP / OPEN → GEN
  EWS       → EWS
  SEBC      → OBC-NCL  (Gujarat's OBC label)
  SC        → SC
  ST        → ST
  TFWS      → flagged via sub_pool (OTHER/TFWS) in the raw/govt-scope long
              files; also surfaced as its own "TFWS" category row in the
              consolidated files (see `_consolidate_5cat()`)
  ESM       → flagged via sub_pool (OTHER/ESM, Ex-Servicemen, horizontal) in
              the raw/govt-scope long files; also surfaced as its own "ESM"
              category row in the consolidated files

  So the "_consolidated_5cat_" files actually carry 7 category values
  (GEN/EWS/OBC-NCL/SC/ST + TFWS/ESM) — the "_5cat_" name is kept as-is for
  continuity even though it's no longer literally 5.

For Avanti JNV GJ student:
  - JNV is Central govt school. Gujarat has no horizontal "govt school
    student" reservation. Compete in regular state quota under their
    GJ vertical category.
  - Engineering: GJ uses the state's own composite formula: GUJCET 1/3 +
    JEE Main 1/3 + Class 12 1/3. The published Home-State cutoff (rank AND
    the percentile-equivalent composite score) is the MERIT POSITION among
    Gujarat applicants, computed from this composite (not GUJCET alone).
  - Pharmacy: no GUJCET involved at all — see the PDF quirk note above.

Output (to extracted_data/):
  - GJ_engg_all_cutoffs_2025.csv                        — long format, all inst types
  - GJ_engg_closing_ranks_govt_2025.csv                 — govt scope, rank + percentile
  - GJ_engg_consolidated_5cat_govt_2025_rank.csv        — 5 verticals + TFWS/ESM, rank basis
  - GJ_engg_consolidated_5cat_govt_2025_percentile.csv  — 5 verticals + TFWS/ESM, percentile basis
  - GJ_pharm_all_cutoffs_2024.csv                       — same shape, pharmacy stream
  - GJ_pharm_closing_ranks_govt_2024.csv
  - GJ_pharm_consolidated_5cat_govt_2024_rank.csv
  - GJ_pharm_consolidated_5cat_govt_2024_percentile.csv
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "extracted_data"
STATE_CODE = "GJ"

# --------------------------------------------------------------------
# Engineering
# --------------------------------------------------------------------
ENGG_SOURCE = ROOT / "source" / "GJ" / "engineering"
ENGG_PHASE_FILE = "GJ_ACPC_2025_Final_RankAndMarks.pdf"
ENGG_SOURCE_URL = ("https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/"
                    "uploads/2026/06/202606121114968955.pdf")
ENGG_DATA_YEAR = 2025
ENGG_CET_NAME = "ACPC-GUJCET"

# (category code, rank column index, marks/percentile column index) in the
# 21-column extracted table. AI columns (17-20) are deliberately excluded.
ENGG_CATEGORY_COLUMNS = [
    ("OP",   3,  4),
    ("SC",   5,  6),
    ("ST",   7,  8),
    ("SEBC", 9,  10),
    ("EWS",  11, 12),
    ("ESM",  13, 14),
    ("TFWS", 15, 16),
]

ENGG_RANK_BASIS = ("Gujarat State Merit Rank, Home-State quota "
                    "(GUJCET 1/3 + JEE Main 1/3 + Class 12 1/3 composite)")
ENGG_PERCENTILE_BASIS = ("Gujarat State Merit composite score (0-100 scale), Home-State quota "
                          "(GUJCET 1/3 + JEE Main 1/3 + Class 12 1/3 composite) "
                          "— labeled 'MARKS' in the source PDF but is a normalized "
                          "composite score, not raw exam marks")

# --------------------------------------------------------------------
# Pharmacy
# --------------------------------------------------------------------
PHARM_SOURCE = ROOT / "source" / "GJ" / "pharmacy"
PHARM_PHASE_FILE = "GJ_ACPC_2024_Pharmacy_Closure.pdf"
PHARM_SOURCE_URL = ("https://acpc.gujarat.gov.in/assets/uploads/media-uploader/"
                     "pharma-closure-2024-251746779890.pdf")
PHARM_DATA_YEAR = 2024  # PDF title: "Admission Year 2024-25" — latest ACPC has published
PHARM_CET_NAME = "ACPC"  # not GUJCET-based, see docstring

# (category code, rank column index, marks column index) in the 19-column
# extracted table. AI columns (17-18) are deliberately excluded.
PHARM_CATEGORY_COLUMNS = [
    ("OPEN", 3,  4),
    ("SC",   5,  6),
    ("ST",   7,  8),
    ("SEBC", 9,  10),
    ("EWS",  11, 12),
    ("ESM",  13, 14),
    ("TFWS", 15, 16),
]

PHARM_RANK_BASIS = "ACPC Merit Rank, Home-State quota (First Year Degree/Diploma Pharmacy)"
PHARM_PERCENTILE_BASIS = ("ACPC Merit composite score (0-100 scale), Home-State quota "
                           "(First Year Degree/Diploma Pharmacy) — labeled 'MERIT MARKS' "
                           "in the source PDF")

# Short standalone words that must never be glued onto the previous line's
# last word, even though they're <=2 chars (guards _join_wrapped_course_name
# against false-positive merges).
_SAFE_SHORT_WORDS = {
    "IN", "OF", "TO", "OR", "AT", "BY", "AN", "IF", "SO", "NO", "GO", "MY",
    "AI", "IT", "US", "UK", "AS", "IS", "BE",
}


def _join_wrapped_course_name(raw: str) -> str:
    """Undo the PDF's forced-character-width line wrapping in course names.

    Unlike institute names (which wrap at word boundaries — plain
    "\\n" -> " " is fine), course-name cells wrap mid-word with no hyphen,
    e.g. "COMMUNICATIO\\nN ENGINEERING". Heuristic: at each line break, glue
    the previous line's last token directly to the next line's first token
    (no space) when that first token is a short (<=2 char) bare-alphabetic
    fragment and not a real short word — that's the tell-tale leftover
    word-ending from a forced break. Verified against all 105 distinct
    course strings in the 2025-26 engineering PDF. (Not needed for pharmacy
    — its institute names wrap at word boundaries only, and Program is a
    plain code with no wrapping.)
    """
    if not raw:
        return raw
    out_tokens: list[str] = []
    for line in raw.split("\n"):
        toks = [t for t in line.split(" ") if t]
        if not toks:
            continue
        if out_tokens and out_tokens[-1].isalpha() and toks[0].isalpha() \
                and len(toks[0]) <= 2 and toks[0].upper() not in _SAFE_SHORT_WORDS:
            out_tokens[-1] += toks[0]
            toks = toks[1:]
        out_tokens.extend(toks)
    return " ".join(out_tokens)


def _num(s: str | None) -> float | None:
    """Parse a rank/marks cell; VAC / No Allotment / ------ / ****** / blank -> None."""
    if s is None:
        return None
    s = s.strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_gj_pdf(path: Path) -> list[dict]:
    """Parse the engineering closure PDF."""
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for r in tbl:
                    if not r or len(r) < 21:
                        continue
                    inst_raw = r[0]
                    if inst_raw is None or inst_raw == "INAME":
                        continue
                    if "Admission Committee" in inst_raw or "Last Admitted Rank" in inst_raw:
                        continue
                    inst = inst_raw.replace("\n", " ").strip()
                    inst_type = (r[1] or "").strip()
                    course = _join_wrapped_course_name((r[2] or "").strip())
                    for cat, rank_i, mark_i in ENGG_CATEGORY_COLUMNS:
                        rank = _num(r[rank_i])
                        if rank is None:
                            continue  # VAC / ------ / ****** — no admission in this category
                        rows.append({
                            "college_name": inst,
                            "institute_type_raw": inst_type,
                            "branch_name": course,
                            "category_raw": cat,
                            "closing_rank": rank,
                            "closing_percentile": _num(r[mark_i]),
                        })
    return rows


def parse_gj_pharmacy_pdf(path: Path) -> list[dict]:
    """Parse the pharmacy closure PDF."""
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for r in tbl:
                    if not r or len(r) < 19:
                        continue
                    inst_raw = r[0]
                    if inst_raw is None or inst_raw == "INAME":
                        continue
                    if any(s in inst_raw for s in
                           ("Admission Committee", "Last Admitted Rank", "Admission Year")):
                        continue
                    inst = inst_raw.replace("\n", " ").strip()
                    program = (r[1] or "").strip()  # Bpharm / Dpharm
                    inst_type = (r[2] or "").strip()
                    for cat, rank_i, mark_i in PHARM_CATEGORY_COLUMNS:
                        rank = _num(r[rank_i])
                        if rank is None:
                            continue  # VAC / No Allotment / ------ / ****** — no admission
                        pct = _num(r[mark_i])
                        if cat == "ESM" and pct == rank:
                            # PDF quirk: ESM_MERIT MARKS duplicates ESM_HS instead of
                            # a real percentile — see docstring. Drop the fabricated value.
                            pct = None
                        rows.append({
                            "college_name": inst,
                            "institute_type_raw": inst_type,
                            "branch_name": program,
                            "category_raw": cat,
                            "closing_rank": rank,
                            "closing_percentile": pct,
                        })
    return rows


def classify_gj_college(inst_type_raw: str, name: str) -> str:
    t = inst_type_raw.strip().upper()
    # "GOV" (engineering PDF) and "GOVT" (pharmacy + old R3 PDF) both occur —
    # check both rather than relying solely on the name-keyword fallback.
    if t in ("GOV", "GOVT") or "GOVERNMENT" in name.upper() or "GOVT" in name.upper():
        return "Govt"
    if t == "GIA":
        return "Govt-Aided"
    if t == "AUTO":
        # IITRAM only (engineering) — state-legislature-established, fully
        # state-funded autonomous technical institute. Closest existing bucket.
        return "State-Univ-Dept"
    if t in ("SFI", "UNI-SFI", "COE", "PPP"):
        return "Private/SF"
    return "Private/SF"


GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


def normalise_category(c: str) -> tuple[str, str]:
    c = c.strip().upper()
    if c in ("OP", "OPEN"): return ("GEN", "")
    if c == "EWS":  return ("EWS", "")
    if c == "SEBC": return ("OBC-NCL", "")
    if c == "SC":   return ("SC", "")
    if c == "ST":   return ("ST", "")
    if c == "TFWS": return ("OTHER", "TFWS")
    if c == "ESM":  return ("OTHER", "ESM")
    return ("OTHER", c)


def _consolidate_5cat(govt_out: pd.DataFrame, value_col: str, basis: str, source_url: str) -> pd.DataFrame:
    # 5 canonical verticals + TFWS/ESM (horizontal sub-pools, carried as
    # category="OTHER"/sub_pool="TFWS"|"ESM" upstream) — pulled in here as
    # their own category values too, per request. Relabel before the
    # groupby so TFWS and ESM don't collapse into one "OTHER" bucket.
    canon = govt_out[
        govt_out["category"].isin(["GEN", "EWS", "OBC-NCL", "SC", "ST"])
        | govt_out["sub_pool"].isin(["TFWS", "ESM"])
    ].copy()
    canon["category"] = canon["category"].where(canon["category"] != "OTHER", canon["sub_pool"])
    canon["branch_code"] = canon["branch_name"]
    canon = canon.groupby([
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code", "branch_name",
        "quota", "category", "gender",
    ], dropna=False).agg(**{
        f"opening_{value_col}": (f"closing_{value_col}", "min"),
        f"closing_{value_col}": (f"closing_{value_col}", "max"),
    }).reset_index()
    canon["last_round_with_max"] = "Final"
    canon["rank_basis"] = basis
    canon["source_url"] = source_url
    return canon


def _run_stream(*, stream_label, out_prefix, year, source_pdf, parse_fn, cet_name,
                 round_text, open_cat_code, rank_basis, percentile_basis, source_url):
    print(f"\n{'=' * 70}\n{stream_label.upper()}\n{'=' * 70}")

    print("Stage 1 — parse PDF")
    rows = parse_fn(source_pdf)
    df = pd.DataFrame(rows)
    print(f"  Total rows: {len(df):,}")
    print(f"  Distinct institutes: {df['college_name'].nunique()}")
    print(f"  Institute types: {df['institute_type_raw'].value_counts().to_dict()}")
    print(f"  Category codes: {sorted(df['category_raw'].unique())}")
    df.to_csv(OUT / f"{out_prefix}_all_cutoffs_{year}.csv", index=False)

    print("\nStage 2 — classify govt scope")
    df["college_type"] = df.apply(
        lambda r: classify_gj_college(r["institute_type_raw"], r["college_name"]),
        axis=1,
    )
    print("  by college_type (distinct colleges):")
    for t, n in (df.groupby(["college_name", "college_type"]).size()
                  .reset_index().college_type.value_counts().items()):
        print(f"    {t:18s} {n:>4} colleges")

    govt = df[df["college_type"].isin(GOVT_TYPES)].copy()
    print(f"  govt-scope colleges: {govt['college_name'].nunique()}")
    print(f"  govt-scope rows:     {len(govt):,}")

    cat_norm = govt["category_raw"].apply(lambda c: pd.Series(normalise_category(c)))
    cat_norm.columns = ["category", "sub_pool"]
    govt = pd.concat([govt, cat_norm], axis=1)

    govt["state"] = "GUJARAT"
    govt["cet_name"] = cet_name
    govt["stream"] = stream_label
    govt["year"] = year
    govt["round"] = round_text
    govt["quota"] = "State (Gujarat domicile)"
    govt["gender"] = "All"  # GJ doesn't split by gender in these PDFs
    govt["college_code"] = govt["college_name"]  # ACPC doesn't expose stable codes here
    govt["rank_basis_per_row"] = rank_basis

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type", "institute_type_raw",
        "branch_name",
        "quota", "category_raw", "category", "sub_pool", "gender",
        "closing_rank", "closing_percentile", "rank_basis_per_row",
    ]].sort_values(["college_name", "branch_name", "category_raw"])
    govt_out["source_url"] = source_url
    govt_out.to_csv(OUT / f"{out_prefix}_closing_ranks_govt_{year}.csv", index=False)

    print("\nStage 3 — schema-canonical 5-cat consolidated (rank + percentile, separate files)")
    canon_rank = _consolidate_5cat(govt_out, "rank", rank_basis, source_url)
    canon_rank.to_csv(OUT / f"{out_prefix}_consolidated_5cat_govt_{year}_rank.csv", index=False)
    print(f"  consolidated 5-cat rows (rank):       {len(canon_rank):,}")

    canon_pct = _consolidate_5cat(govt_out, "percentile", percentile_basis, source_url)
    canon_pct.to_csv(OUT / f"{out_prefix}_consolidated_5cat_govt_{year}_percentile.csv", index=False)
    print(f"  consolidated 5-cat rows (percentile): {len(canon_pct):,}")

    print(f"\n=== {stream_label} sanity (govt scope, {open_cat_code}, hardest 12 by rank) ===")
    sample = govt_out[govt_out["category_raw"] == open_cat_code].sort_values("closing_rank").head(12)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_rank", "closing_percentile"]]
              .to_string(index=False, max_colwidth=55))

    return govt_out


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    _run_stream(
        stream_label="engineering",
        out_prefix=f"{STATE_CODE}_engg",
        year=ENGG_DATA_YEAR,
        source_pdf=ENGG_SOURCE / ENGG_PHASE_FILE,
        parse_fn=parse_gj_pdf,
        cet_name=ENGG_CET_NAME,
        round_text="Final (Online Round, ACPC closure data)",
        open_cat_code="OP",
        rank_basis=ENGG_RANK_BASIS,
        percentile_basis=ENGG_PERCENTILE_BASIS,
        source_url=ENGG_SOURCE_URL,
    )

    _run_stream(
        stream_label="pharmacy",
        out_prefix=f"{STATE_CODE}_pharm",
        year=PHARM_DATA_YEAR,
        source_pdf=PHARM_SOURCE / PHARM_PHASE_FILE,
        parse_fn=parse_gj_pharmacy_pdf,
        cet_name=PHARM_CET_NAME,
        round_text="Final (Online Rounds completed, ACPC closure data)",
        open_cat_code="OPEN",
        rank_basis=PHARM_RANK_BASIS,
        percentile_basis=PHARM_PERCENTILE_BASIS,
        source_url=PHARM_SOURCE_URL,
    )


if __name__ == "__main__":
    main()
