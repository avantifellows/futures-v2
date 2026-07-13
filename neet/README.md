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

Not yet parsed (bespoke work): Kerala (rank is a **state** rank, needs AIR conversion),
Telangana / Maharashtra / Himachal (no clean table grid).

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
# one source
python3 scrape/scripts/03_parse_karnataka.py
# flat states (all three)
python3 scrape/scripts/04_parse_flat_states.py --all
```

Requires `pdfplumber`. The AIQ parse reads ~3,000 pages across two PDFs and takes several
minutes; the state files are fast.

## Score → rank model

The marks→AIR model that turns a student's NEET score into a rank lives in the
`college-predictor` repo (`scripts/fit_score_rank_model.py`), calibrated from the
Telangana merit list + MP + Punjab score/rank pairs. It is a predictor artifact, not a
published cutoff, so it does not live here.
