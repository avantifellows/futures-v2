"""
Invariant scanner for the Maharashtra CET parsers (engineering / pharmacy /
bdesign / architecture).

Ported from the rule-set we settled on during the NEET-UG parser audit. The
point is not to prove the data right — it can't — but to make a specific set
of silent-corruption modes loud, and to give a single number that has to go
down (with every survivor individually explained) before a refresh ships.

    python validate_MH.py                 # every stream found in extracted_data/
    python validate_MH.py engineering     # one stream

Rules
  R1  absurd rank           rank above the plausible ceiling for the stream
  R2  ordering inversion    OPEN closes LATER than a reserved category at the
                            same (college, branch, quota) — reserved seats
                            should not be harder than open ones
  R3  duplicate bucket      same (college, branch, quota, category, type) twice
                            with different closing ranks -> group-key failure
  R4  mangled text          college/branch/status carrying page boilerplate
  R5  opening > closing     MIN/MAX inverted
  R6  category is a quota   a seat/quota token sitting in the category column

Exit code is 0 always — this is a report, not a gate. Read the numbers.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "extracted_data"

# MHT-CET publishes a *state* merit rank. 2025 engineering had ~4.5 lakh
# candidates, so a few hundred thousand is ordinary at the thin tail; past
# ~6 lakh is not credible for any stream. Deliberately loose: a tight ceiling
# here manufactures false positives, which is how the NEET scan lost its
# usefulness the first time round.
RANK_CEILING = 600_000

# Page furniture that must never survive into a name/status field.
#
# NOTE "Home University : <X>" is deliberately NOT here. It looks like
# contamination but the CET Cell prints it on the same source line as
# "Status:", so it is legitimate text — flagging it produced 10,752 false
# positives on the first pass and buried the real signal.
BOILERPLATE = (
    "for the Year",
    "Maharashtra State Seats",
    "Figures in bracket",
    "Cut Off",
    "Legends",
    "Page ",
    "Government of Maharashtra",
    "State Common Entrance",
)

# Tokens that describe a SEAT or a QUOTA, not a candidate's social category.
QUOTA_TOKENS = {
    "AI", "MI", "MIN", "MINO", "TFWS", "ORPHAN", "EMOBC", "EMSEBC",
    "MANAGEMENT", "MGMT", "NRI", "IQ", "I.Q.", "PAY", "PAID",
}

OPEN_CATS = {"GOPENS", "GOPENH", "GOPENO", "LOPENS", "LOPENH", "LOPENO"}
RESERVED_PREFIX = ("GOBC", "LOBC", "GSC", "LSC", "GST", "LST",
                   "GVJ", "LVJ", "GNT", "LNT", "GSEBC", "LSEBC")


def _load(stream: str) -> pd.DataFrame | None:
    for name in (f"MH_{stream}_state_quota_closing_ranks_2025.csv",
                 f"MH_{stream}_state_quota_closing_ranks_2025.csv"):
        p = OUT / name
        if p.exists():
            return pd.read_csv(p)
    return None


def scan(stream: str, df: pd.DataFrame) -> int:
    print(f"\n{'=' * 72}\n{stream}  —  {len(df):,} closing-rank rows\n{'=' * 72}")
    total = 0

    # ---- R1 absurd rank -------------------------------------------------
    bad = df[df["closing_rank"] > RANK_CEILING]
    print(f"R1  rank > {RANK_CEILING:,}                     : {len(bad):>6,}")
    if len(bad):
        print(bad.nlargest(3, "closing_rank")[
            ["college_name", "category_raw", "closing_rank"]].to_string(index=False))
    total += len(bad)

    # ---- R2 ordering inversion -----------------------------------------
    # Compare each group's OPEN closing rank against its reserved categories.
    # A *near* tie is normal (thin pools fill unpredictably); only flag when
    # OPEN is materially worse, which is what a contaminated bucket looks like.
    inv = 0
    keys = ["college_code", "branch_code", "quota"]
    for _, g in df.groupby(keys, dropna=False):
        op = g[g["category_raw"].isin(OPEN_CATS)]["closing_rank"]
        if op.empty:
            continue
        open_close = op.max()
        res = g[g["category_raw"].astype(str).str.startswith(RESERVED_PREFIX)]
        if res.empty:
            continue
        # OPEN worse than the *tightest* reserved seat by a wide margin.
        #
        # Calibration: at 1.5x this fires 111 times in engineering, but 94 of
        # those reserved pools hold a SINGLE seat — a 1-seat NT3/SEBC pool
        # closes at whoever happened to apply, while the open pool runs to the
        # tail. That is real MHT-CET behaviour, not corruption, and the govt-
        # scope hits all sat in a tight 1.5-2.2x band. Contamination of the
        # kind this rule exists to catch shows up an order of magnitude out,
        # so the bar is 4x AND a pool deep enough to mean something.
        tight = res.loc[res["closing_rank"].idxmin()]
        deep_enough = tight.get("num_rank_observations", 1) >= 3
        if open_close > tight["closing_rank"] * 4 and deep_enough:
            inv += 1
    print(f"R2  OPEN >4x later than a deep reserved   : {inv:>6,}")
    total += inv

    # ---- R3 duplicate bucket -------------------------------------------
    k = ["college_code", "branch_code", "quota", "category_raw", "college_type"]
    k = [c for c in k if c in df.columns]
    nun = df.groupby(k, dropna=False)["closing_rank"].nunique()
    dup = int((nun > 1).sum())
    print(f"R3  duplicate buckets w/ diff closing     : {dup:>6,}")
    total += dup

    # ---- R4 mangled text ------------------------------------------------
    mang = 0
    for col in ("college_name", "branch_name", "status"):
        if col not in df.columns:
            continue
        hit = df[df[col].astype(str).str.contains("|".join(BOILERPLATE), na=False)]
        if len(hit):
            print(f"R4  boilerplate in {col:13s}          : {len(hit):>6,}")
            print("      e.g.", repr(hit[col].iloc[0][:90]))
        mang += len(hit)
    if not mang:
        print(f"R4  boilerplate in name/status fields     : {0:>6,}")
    total += mang

    # ---- R5 opening > closing ------------------------------------------
    if "opening_rank" in df.columns:
        bad5 = df[df["opening_rank"] > df["closing_rank"]]
        print(f"R5  opening_rank > closing_rank           : {len(bad5):>6,}")
        total += len(bad5)

    # ---- R6 category is really a quota ---------------------------------
    # A quota token in category_raw is fine on its own — that IS what the PDF
    # prints. It's only a bug if it leaks through UNNORMALISED, i.e. lands in
    # the canonical `category` column instead of being bucketed to OTHER with
    # sub_pool set. MI / TFWS / ORPHAN all normalise correctly today.
    cats = df["category_raw"].astype(str).str.upper()
    suspect = df[cats.isin(QUOTA_TOKENS)]
    if "category" in df.columns:
        bad6 = suspect[suspect["category"].astype(str).str.upper().isin(QUOTA_TOKENS)]
    else:
        bad6 = suspect
    print(f"R6  quota token leaked into category      : {len(bad6):>6,}")
    if len(bad6):
        print("      tokens:", sorted(bad6["category_raw"].unique())[:8])
    elif len(suspect):
        print(f"      ({len(suspect):,} quota-ish category_raw values, all "
              f"normalised to OTHER+sub_pool — not a bug)")
    total += len(bad6)

    print(f"\n  TOTAL flagged: {total:,}")
    return total


def main() -> None:
    streams = sys.argv[1:] or ["engg", "pharm", "bdesign"]
    grand = 0
    for s in streams:
        df = _load(s)
        if df is None:
            print(f"\n(no closing-ranks CSV for stream '{s}' — skipped)")
            continue
        grand += scan(s, df)
    print(f"\n{'=' * 72}\nGRAND TOTAL flagged across streams: {grand:,}\n{'=' * 72}")


if __name__ == "__main__":
    main()
