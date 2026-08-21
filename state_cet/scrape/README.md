# state_cet/scrape/ — upstream scraper (copied from College DB)

Verbatim copy of the state-CET scrape pipeline from the `College DB` repo
(`state-cet-scrape/`), brought over so this source owns the full scrape→load chain.

- **`scripts/`** (committed) — 18 per-state download + parse scripts +
  `consolidate_all.py`.
- **`source/`** (gitignored, ~117 MB in the bundle, belongs in GCS) — the raw
  cutoff PDFs/HTML per state.

## Superseded: Andhra Pradesh

`scripts/state_AP.py` is superseded by **external_data_sources/apeapcet/** -
the 2025 consolidated last ranks from the live CAP portal replace this
file's 2022 proxy; BQ `apeapcet_fact_cutoffs`, open-data published, predictor
exam live. AP remains here only as an input to the consolidated 5-cat CSV.

## Superseded: Kerala

`scripts/state_KL.py` is superseded by **external_data_sources/keam/** (2025 +
the live 2026 cycle, BQ `keam_fact_cutoffs`, open-data published, and a fix
for this parser's page-spill course bug). KL remains here only as an input to
the consolidated 5-cat CSV.

## Superseded: West Bengal

`scripts/state_WB.py` is superseded by **external_data_sources/wbjee/** (six
years 2021-2026 incl. the live 2026 cycle, BQ `wbjee_fact_cutoffs`, open-data
published). WB remains here only as an input to the consolidated 5-cat CSV.

## ⚠️ Copied as-is — not yet decoupled

Written for the College DB layout; paths point at that repo's `source/<XX>/` and
`extracted_data/`. **Will not run unmodified here** without re-pathing. Until
decoupled, refresh by running the pipeline in College DB and copying its
`extracted_data/ALL_STATES_consolidated_5cat_govt.csv` into `state_cet/raw/`.

### Decoupled exception: KCET 2025 detailed cutoffs

`scripts/parse_KA_2025.py` runs directly in this repository. Place the two
official KEA Third Round PDFs at:

- `source/KA/engineering/KA_engg_2025_GEN_R3.pdf`
- `source/KA/engineering/KA_engg_2025_HK_R3.pdf`

Then run `python scripts/parse_KA_2025.py --dry-run` to validate or omit
`--dry-run` to write
`extracted_data/KA_engg_2025_all_cutoffs_R3.csv`. The parser fails closed on
layout/category drift, preserves raw and normalized course labels, handles
header-only continuation pages, and retains wrapped fractional ranks. The
static 2025 anchors are 13,604 rows, 229 colleges, 140 course labels, and 47
category codes.

## Chain that produces the neutral fact

Per-state `state_<XX>.py` / `download_<XX>.py` parse each authority's PDFs →
`consolidate_all.py` unions + applies the govt-scope + 5-cat harmonization →
`ALL_STATES_consolidated_5cat_govt.csv` = `state_cet/raw/` (what our
`build_clean.py` reads). The harmonization is the "curated product" this source
intentionally ships (see ../CLAUDE.md).
