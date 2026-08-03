# neet/

NEET-UG 2025 medical/dental admission **closing-rank cutoffs**, parsed from the
official counselling PDFs into clean CSVs the college predictor consumes.

Two families of cutoff:
- **All India Quota (AIQ)** — the MCC-counselled 15% national seats. One national file.
- **State quota** — each state's own counselling (~85% of govt seats). One file per state,
  each with its own layout, category taxonomy, and (sometimes) rank space.

These CSVs feed `college-predictor` (`scripts/generate_neet_data.py` →
`public/data/NEETUG/NEETUG.json`). Staging to GCS/BigQuery is a later step.

## Sources (2025 cycle)

| Parser | State | Round | Shape | Rank space |
|---|---|---|---|---|
| `01_parse_aiq.py` | All India (MCC) | R1+R3 | per-student ledger → pivot | NEET AIR |
| `02_parse_gujarat.py` | Gujarat | R3 | pre-computed wide grid (has score) | NEET AIR |
| `03_parse_karnataka.py` | Karnataka | R3 | per-student table (KEA codes) | NEET AIR |
| `04_parse_flat_states.py` | West Bengal / Madhya Pradesh / Punjab | R1/R1/R2 | flat per-student tables | NEET AIR |
| `05_parse_andhra.py` | Andhra Pradesh | R3 | section-header (college as a row) | NEET AIR |
| `06_parse_maharashtra.py` | Maharashtra | R3 | space-aligned text; category segment decoded | NEET AIR |
| `07_parse_telangana.py` | Telangana | Mop-up | text, `COLL ::` section headers | NEET AIR |
| `08_parse_himachal.py` | Himachal Pradesh | R3 | clean table | NEET AIR |
| `09_parse_kerala.py` | Kerala | P3 | table; state-rank → AIR via rank-list crosswalk | NEET AIR (converted) |

All 11 sources (AIQ + 10 states) are parsed. See "Known limitations" below for the
per-source caveats (mop-up phase, converted ranks, inferred MBBS/BDS, etc.).

## Cutoff definition

For per-student files, the closing rank for a (college, category, program) bucket is the
**max AIR** among students finally allotted there. AIQ unions the MCC **R1 result** (which
carries category for every allotted student, including R1-retained toppers the R3 ledger
leaves blank) with the **R3** fresh-allotments/upgrades (which loosen closing ranks as
seats free up). R1 and R3 differ materially — median closing rank shifts ~21%, so the
union is necessary, not cosmetic.

## Pipeline shape

```
neet/scrape/source/<file>.pdf            (gitignored — official counselling PDFs)
       │  scrape/scripts/NN_parse_*.py    pdfplumber → pivot → clean CSV
       ▼
neet/scrape/extracted_data/neet_<src>_2025_cutoffs.csv   (gitignored)
       │  consumed by college-predictor/scripts/generate_neet_data.py
       ▼
college-predictor public/data/NEETUG/NEETUG.json
```

Each CSV carries: `Institute, Category, Academic Program Name, Seat Type, Round,
Closing Rank, rank_space` (Gujarat also keeps `NEET Score` / `Percentile`).

## Running

```bash
python3 scrape/scripts/run_all.py            # every source
python3 scrape/scripts/03_parse_karnataka.py # one source
python3 scrape/scripts/04_parse_flat_states.py --all   # WB / MP / Punjab
```

Requires `pdfplumber`. The AIQ parse (~3,000 pages across two PDFs) and the Kerala
crosswalk build (~520-page rank list) each take a few minutes; the rest are fast.

## Score → rank model

The marks→AIR model that turns a student's NEET score into a rank lives in the
`college-predictor` repo (`scripts/fit_score_rank_model.py`), calibrated from the
Telangana merit list + MP + Punjab score/rank pairs. It is a predictor artifact, not a
published cutoff, so it does not live here.

## Known limitations & things to review

Per-source caveats worth a human check before treating any of these as authoritative:

- **Telangana is MOP-UP phase data.** The TG allotment file is the mop-up (last)
  round, where only leftover seats remain — so its closing ranks are much *looser*
  than the main counselling rounds (e.g. Osmania OPEN closes ~AIR 439k here). If a
  main-round TG allotment becomes available, prefer it.
- **Kerala rank→AIR is converted, not native.** Kerala's file lists a Kerala state
  rank; we convert to NEET AIR via the KEAM state medical rank list crosswalk
  (`mbbsranklist.pdf`). 17/6,708 rows couldn't be mapped (dropped).
- **MBBS/BDS is inferred from the college name** for Maharashtra, Himachal, Kerala
  (their files don't label degree per row) using Amogh's MC/MED→MBBS, DC→BDS
  heuristic. Kerala has **23 buckets flagged `REVIEW`** (2 ambiguous names: Azeezia
  "Medi Science", MES "MED-" Dental) that need manual assignment.
- **Rounds differ by state** — R1 (WB, Punjab, MP), R3 (most), mop-up (TG). Labelled
  per row in `Round`. R1-only states have tighter cutoffs than fuller-round states.
- **Big/cryptic category lists.** Karnataka (~42 codes) and Maharashtra (~63, once
  female/home-univ/EWS-minority splits are folded in) produce long dropdowns — a UX
  curation decision for the predictor.
- **BSc Nursing coverage is minimal** — only a handful of AIQ nursing seats; state
  files here are MBBS/BDS.
