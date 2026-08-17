"""
Telangana TG-EAPCET (formerly TS EAMCET) — engineering closing-ranks pipeline.

Authority:  TGCHE (Telangana State Council of Higher Education)
            + Convener TG-EAPCET / JNTU Hyderabad
Portal:     https://tgeapcetd.nic.in/files/  (2025 Last Rank Statements are
            published here directly — the older tgeapcet.nic.in mirror used
            for 2024 no longer serves these files).
Source:     TG-EAPCET 2025 Last Rank Statements (First Phase, Second Phase,
            Final Phase), downloaded directly from tgeapcetd.nic.in. This is
            the actual 2025 counselling data — no longer a 2024-as-proxy.
            Direct download links (place under source/TG/engineering/):
              https://tgeapcetd.nic.in/files/TGEAPCET_2025_LASTRANKS_FirstPhase.pdf
              https://tgeapcetd.nic.in/files/TGEAPCET_2025_LASTRANKS_SecondPhase.pdf
              https://tgeapcetd.nic.in/files/TGEAPCET_2025_FINALPHASE_LASTRANKS.pdf

PDF format (clean tabular, pdfplumber extracts cleanly):
  31 columns per (college, branch) row:
    Inst Code | Institute Name | Place | Dist Code | Co Education |
    College Type (PVT/UNIV/SF/GOV) | Branch Code | Branch Name |
    OC_BOYS | OC_GIRLS | BC_A BOYS | BC_A GIRLS | BC_B BOYS | BC_B GIRLS |
    BC_C BOYS | BC_C GIRLS | BC_D BOYS | BC_D GIRLS | BC_E BOYS | BC_E GIRLS |
    SC_I BOYS | SC_I GIRLS | SC_II BOYS | SC_II GIRLS | SC_III BOYS |
    SC_III GIRLS | ST_BOYS | ST_GIRLS | EWS_BOYS | EWS_GIRLS | Affiliated To

  Changed vs the 2024 PDF format:
    - No "Year of Estab" column (Branch Code shifts from col 7 → col 6).
    - No "Tuition Fee" column (Affiliated To is now the last column).
    - SC is split into SC_I / SC_II / SC_III (2024 SC Rationalization GO
      sub-categories) instead of one SC column — same split already used
      in state_medical's TG NEET pipeline.
    - EWS has no "_OU" suffix / OU-only caveat — it's a plain EWS column,
      not scoped to the Osmania local-area sub-pool the way the 2024 PDF's
      EWS_GEN_OU / EWS_GIRLS_OU columns were.
    - "College Type" values are PVT / UNIV / SF / GOV — note "GOV", not
      "GOVT", and a new "SF" value (self-finance stream within a state
      university, e.g. JNAFAU School of Planning — Self Finance). SF is
      not govt-subsidized, so it's classified as Private/SF, same as PVT.

Reservation taxonomy (Telangana):
  Vertical (caste): OC / BC_A / BC_B / BC_C / BC_D / BC_E / SC_I / SC_II /
                     SC_III / ST + EWS
  Horizontal: BOYS / GIRLS (33% women's reservation embedded)
  Local-area sub-pools (OU / KU / TGUR) are not exposed as separate columns
  in this PDF — closing ranks shown are the headline (all-local-area) ranks.

For canonical 5-cat mapping (NCST schema):
  OC                                  → GEN
  BC_A, BC_B, BC_C, BC_D, BC_E        → OBC-NCL (TG's BC sub-list — approximate)
  SC_I, SC_II, SC_III                 → SC
  ST                                  → ST
  EWS                                 → EWS

For Avanti JNV TG student:
  - JNV is Central govt school — no horizontal "govt school student"
    reservation in TG. Compete in regular OC/BC*/SC*/ST per caste category.
  - Local area: most JNV districts in TG would be OU (Osmania); Warangal/
    Karimnagar/Khammam districts → KU. The PDF doesn't expose local area
    explicitly per row, so we use the headline closing rank.

Methodology: TG publishes First Phase, Second Phase, and Final Phase
last-rank PDFs. Final Phase = cumulative through the last main allotment
round. Stray vacancy rounds excluded. We use Final Phase as the
authoritative closing rank.

Output (to extracted_data/):
  - TG_engg_all_cutoffs_2025.csv         — long, every (college, branch, cat) cell
  - TG_engg_closing_ranks_govt_2025.csv  — govt scope
  - TG_engg_consolidated_5cat_govt_2025.csv  — schema-canonical
"""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source" / "TG" / "engineering"
OUT = ROOT / "extracted_data"
STATE_CODE = "TG"
DATA_YEAR = 2025
CET_NAME = "TG-EAPCET"
SOURCE_URL = "https://tgeapcetd.nic.in/"

PHASE_FILES = [
    ("TGEAPCET_2025_LASTRANKS_FirstPhase.pdf",  "P1"),
    ("TGEAPCET_2025_LASTRANKS_SecondPhase.pdf", "P2"),
    ("TGEAPCET_2025_FINALPHASE_LASTRANKS.pdf",  "PFinal"),  # ← used for closing
]

# Cell column → (canonical_category, gender)
CELL_COLUMNS = [
    # (col_idx, raw_label, canonical_cat, gender)
    (8,  "OC_BOYS",       "GEN",      "Boys"),
    (9,  "OC_GIRLS",      "GEN",      "Girls"),
    (10, "BC_A_BOYS",     "OBC-NCL",  "Boys"),
    (11, "BC_A_GIRLS",    "OBC-NCL",  "Girls"),
    (12, "BC_B_BOYS",     "OBC-NCL",  "Boys"),
    (13, "BC_B_GIRLS",    "OBC-NCL",  "Girls"),
    (14, "BC_C_BOYS",     "OBC-NCL",  "Boys"),
    (15, "BC_C_GIRLS",    "OBC-NCL",  "Girls"),
    (16, "BC_D_BOYS",     "OBC-NCL",  "Boys"),
    (17, "BC_D_GIRLS",    "OBC-NCL",  "Girls"),
    (18, "BC_E_BOYS",     "OBC-NCL",  "Boys"),
    (19, "BC_E_GIRLS",    "OBC-NCL",  "Girls"),
    (20, "SC_I_BOYS",     "SC",       "Boys"),
    (21, "SC_I_GIRLS",    "SC",       "Girls"),
    (22, "SC_II_BOYS",    "SC",       "Boys"),
    (23, "SC_II_GIRLS",   "SC",       "Girls"),
    (24, "SC_III_BOYS",   "SC",       "Boys"),
    (25, "SC_III_GIRLS",  "SC",       "Girls"),
    (26, "ST_BOYS",       "ST",       "Boys"),
    (27, "ST_GIRLS",      "ST",       "Girls"),
    (28, "EWS_BOYS",      "EWS",      "Boys"),
    (29, "EWS_GIRLS",     "EWS",      "Girls"),
]


def parse_tg_phase_pdf(pdf_path: Path, phase_label: str) -> list[dict]:
    """Parse one TG-EAPCET phase Last Rank PDF; return cell-level rows."""
    rows: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for tbl in tables:
                for r in tbl:
                    if not r or len(r) < 30:
                        continue
                    code = (r[0] or "").strip()
                    # Header rows have no 3+-letter code
                    if not (len(code) >= 3 and code.isalpha() and code.isupper()):
                        continue
                    branch_code = (r[6] or "").strip()
                    if not branch_code:
                        continue
                    college = (r[1] or "").strip()
                    place = (r[2] or "").strip()
                    dist = (r[3] or "").strip()
                    coed = (r[4] or "").strip()
                    coll_type = (r[5] or "").strip().upper()
                    branch_name = (r[7] or "").strip()
                    affiliated = (r[30] or "").strip() if len(r) > 30 else ""

                    for col_idx, raw_lbl, cat, gender in CELL_COLUMNS:
                        if col_idx >= len(r):
                            continue
                        v = (r[col_idx] or "").strip()
                        if not v or v in ("--", "-"):
                            continue
                        try:
                            rank = int(v.replace(",", ""))
                        except ValueError:
                            continue
                        rows.append({
                            "phase": phase_label,
                            "college_code": code,
                            "college_name": college,
                            "place": place,
                            "dist": dist,
                            "coed": coed,
                            "college_type_raw": coll_type,
                            "branch_code": branch_code,
                            "branch_name": branch_name,
                            "category_raw": raw_lbl,
                            "category": cat,
                            "gender": gender,
                            "closing_rank": rank,
                            "affiliated_to": affiliated,
                        })
    return rows


def classify_tg_college(coll_type_raw: str, college_name: str, affiliated: str) -> str:
    """Govt scope classifier.
    PDF has 'PVT' / 'UNIV' / 'SF' / 'GOV' in college_type column. Use that
    as primary. 'SF' (self-finance stream within a state university, e.g.
    JNAFAU School of Planning — Self Finance) is not govt-subsidized, so
    it's treated like PVT.
    """
    t = coll_type_raw.strip().upper()
    if t in ("GOVT", "GOV"):
        return "Govt"
    if t == "UNIV":
        return "State-Univ-Dept"
    return "Private/SF"


GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parse TG phase PDFs (P1, P2, FinalPhase)")
    all_rows = []
    for fname, phase in PHASE_FILES:
        path = SOURCE / fname
        if not path.exists():
            print(f"  ✗ {fname} missing")
            continue
        rows = parse_tg_phase_pdf(path, phase)
        print(f"  {fname:55s} {phase:8s}: {len(rows):,} cell rows")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    print(f"\n  TOTAL all-phases: {len(df):,} cell rows")
    print(f"  Distinct colleges: {df['college_code'].nunique()}")
    print(f"  Distinct (college × branch): "
          f"{df.groupby(['college_code','branch_code']).ngroups}")
    df.to_csv(OUT / f"{STATE_CODE}_engg_all_cutoffs_{DATA_YEAR}.csv", index=False)

    # college_name/branch_name/place/affiliated_to wrap across lines in the
    # PDF, and the wrap point isn't stable between phase files (e.g. P1 has
    # "ELECTRONICS AND COMMUNICATION ENGINEERING", P2 has "ELECTRONICS AND
    # COMMUNICATION\nENGINEERING" for the exact same seat). Left as-is, that
    # turns one seat into two groupby keys below, so MAX(rank) never compares
    # them against each other and the "closing rank" can come from whichever
    # phase happened to keep the higher-numbered variant.
    #
    # A plain "collapse \s+ to one space" isn't enough on its own: some wraps
    # split a single word mid-token with no real space there at all (e.g.
    # "MAHABUBABA\nD" should rejoin to "MAHABUBABAD", not "MAHABUBABA D" —
    # collapsing the newline to a space leaves it looking like two words and
    # still failing to match the un-wrapped "MAHABUBABAD" from another phase).
    # So we group on an ALL-whitespace-stripped match key, which collides
    # correctly regardless of *where* a wrap landed, and separately pick the
    # most common cleanly-spaced spelling per group for display — the same
    # "pick the mode across phases" trick already used for last_phase_with_max.
    def _clean(s):
        return re.sub(r"\s+", " ", str(s)).strip()

    def _match_key(s):
        return re.sub(r"\s+", "", str(s)).upper()

    for c in ("college_name", "branch_name", "place", "affiliated_to"):
        df[f"{c}_key"] = df[c].map(_match_key)
        df[c] = df[c].map(_clean)

    print("\nStage 2 — closing ranks: take MAX(rank) across all 3 phases")
    closing = (df.groupby(
        ["college_code", "college_name_key", "place_key", "dist", "coed",
         "college_type_raw", "branch_code", "branch_name_key",
         "category_raw", "category", "gender", "affiliated_to_key"],
        dropna=False,
    ).agg(
        college_name=("college_name", lambda s: s.value_counts().index[0]),
        place=("place", lambda s: s.value_counts().index[0]),
        branch_name=("branch_name", lambda s: s.value_counts().index[0]),
        affiliated_to=("affiliated_to", lambda s: s.value_counts().index[0]),
        opening_rank=("closing_rank", "min"),
        closing_rank=("closing_rank", "max"),
        last_phase_with_max=("phase",
                              lambda s: s.value_counts().index[0]),
    ).reset_index())
    print(f"  closing-rank rows (all colleges): {len(closing):,}")

    print("\nStage 3 — classify govt scope")
    closing["college_type"] = closing.apply(
        lambda r: classify_tg_college(r["college_type_raw"], r["college_name"], r["affiliated_to"]),
        axis=1,
    )
    print("  by college_type:")
    for t, n in (closing.groupby(["college_code","college_type"]).size()
                  .reset_index().college_type.value_counts().items()):
        print(f"    {t:18s} {n:>4} colleges")

    govt = closing[closing["college_type"].isin(GOVT_TYPES)].copy()
    print(f"  govt-scope colleges: {govt['college_code'].nunique()}")
    print(f"  govt closing-rank rows: {len(govt):,}")

    govt["state"] = "TELANGANA"
    govt["cet_name"] = CET_NAME
    govt["stream"] = "engineering"
    govt["year"] = DATA_YEAR
    govt["round"] = "P1+P2+PFinal cumulative (last-rank PDFs)"
    govt["quota"] = "State (TG domicile)"
    govt["rank_basis"] = "TG-EAPCET State Rank"
    govt["source_url"] = SOURCE_URL

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code", "branch_name",
        "quota", "category_raw", "category", "gender",
        "opening_rank", "closing_rank", "last_phase_with_max",
        "rank_basis", "source_url",
    ]].sort_values(["college_code", "branch_code", "category_raw", "gender"])
    govt_out.to_csv(
        OUT / f"{STATE_CODE}_engg_closing_ranks_govt_{DATA_YEAR}.csv", index=False,
    )

    # 5-cat consolidated (BC_A...BC_E aggregated to OBC-NCL, SC_I..SC_III to SC)
    print("\nStage 4 — schema-canonical 5-cat consolidated")
    canon = govt.groupby(
        ["state", "cet_name", "stream", "year", "round",
         "college_code", "college_name", "college_type",
         "branch_code", "branch_name",
         "quota", "category", "gender"],
        dropna=False,
    ).agg(
        opening_rank=("opening_rank", "min"),
        closing_rank=("closing_rank", "max"),
        last_round_with_max=("last_phase_with_max",
                              lambda s: s.value_counts().index[0]),
    ).reset_index()
    canon["rank_basis"] = "TG-EAPCET State Rank"
    canon["source_url"] = SOURCE_URL
    canon.to_csv(
        OUT / f"{STATE_CODE}_engg_consolidated_5cat_govt_{DATA_YEAR}.csv", index=False,
    )
    print(f"  consolidated 5-cat rows: {len(canon):,}")

    # Sanity check
    print("\n=== TG sanity (govt scope, GEN/Boys, hardest 10) ===")
    sample = govt_out[
        (govt_out["category_raw"] == "OC_BOYS")
    ].sort_values("closing_rank").head(10)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_rank"]]
              .to_string(index=False, max_colwidth=55))


if __name__ == "__main__":
    main()
