---
name: external-datasets
description: >
  Add or update a public/external dataset in the avantifellows/external_data_sources
  repo and its BigQuery dataset (avantifellows.external_data_sources), plus the paired
  bq-assistant schema + analysis-intent docs. Use when ingesting a new source (e.g.
  AISHE, AICTE, UDISE, NMC, NAS, PLFS, DCI/BDS), reshaping a table, writing/reviewing
  the schema YAMLs, or loading the tables into BigQuery. Encodes the team's pipeline
  model, repo conventions, one-table-at-a-time merge process, the BQ load runbook, and
  the documentation standard (schema docs must TEACH the domain, not assume it).
---

# Adding to external datasets

The end-to-end, fully regenerable model for getting a public dataset into
`avantifellows.external_data_sources` (BigQuery, region `asia-south1`) and into the
BQ assistant. Two repos, one GCS bucket. **Data never lives in git.**

```
source URL ──fetch──▶ gs://avantifellows-external-data/<source>/raw/   (raw files, gitignored locally)
                          │ clean/parse/transform script
                          ▼
                     gs://avantifellows-external-data/<source>/clean/  (clean parquet — the bytes BQ loads)
                          │ bq load / load_bq.py
                          ▼
   avantifellows.external_data_sources.<source>_fact_* / _dim_*        (selective, denormalized wide tables)
```

## The two repos — what goes where

| | `avantifellows/external_data_sources` | `avantifellows/bq-assistant` |
|---|---|---|
| Holds | The **pipeline**: fetch + transform/clean + `upload_to_gcs.py` + `load_bq.py` + `sources.py`, the `schemas/*.yaml`, small `codemaps/*.csv`, README/CLAUDE | A **copy** of each table's schema YAML at `docs/schemas/external_data_sources/<table>.yaml` + the analysis-intent catalog `docs/analyses/external_data_sources.yaml` |
| Source of truth for | HOW the data is built | What the assistant grounds SQL in |
| After edits | — | regenerate `CLAUDE.md` via `scripts/regen_claude_md.py` (CI-checked) |

- **In git (external_data_sources):** ALL pipeline scripts (incl. the raw→clean transform recipe — this is what makes the data auditable/regenerable), schema YAMLs, small codemaps, docs.
- **Never in git:** raw source files, clean parquet, large outputs — those live in GCS. Each source folder has a `.gitignore` guarding `raw/`, `clean/`, `outputs/`.
- **Not in this repo at all:** analysis code/outputs. Exploratory analysis runs locally; analysis *intents* are documented in bq-assistant.

Per-source folder: `scripts/  schemas/  codemaps/  raw/(gitignored)  clean/(gitignored)`.
Reference implementations to copy: `nirf/` (light pass-through), `plfs/` (heavy parse), `jnv/` (raw+clean both staged).

## Naming & schema design

- Tables: `<source>_fact_*` / `<source>_dim_*`. Schema YAML filename matches the table name exactly.
- Prefer a **small number of wide fact tables** (one per source where possible). Denormalize aggressively per use case.
- For a single fact that covers multiple grains, use an **`"All"` sentinel** on the dims a given cut doesn't break out, AND add a **`cut` discriminator column** so the assistant never sums across grains by accident. Never sum across the 'All' rows.
- **Hierarchical dims** (industry/occupation/geography classifications) stay as separate `_dim_*` tables — analysts query their structure. **Small enums** (sex, sector, …) are denormalized inline as `*_label` columns on the fact, NOT as per-enum dim tables.
- **All codes are STRING**, zero-padded as in the source (`'01'`, `'62011'`). INT loses padding and breaks joins. Geography/district codes are scoped per parent — join on the composite key.
- Derived rollups/projections are analysis SQL, not extra tables.

## Documentation standard — schema docs must TEACH, not just name

The single most important review lesson: **a reader who has never used this dataset must be able to understand it from the schema file alone.** Naming a concept ("NIC 2008 hierarchy: division → group → class → subclass") is NOT enough — explain what it *is* and what each piece *means*.

Every `_dim_` / `_fact_` schema's top `description` must cover, in plain language:

1. **What the source / concept is** — e.g. "NIC = National Industrial Classification: India's official scheme for classifying an economic unit by the kind of activity it does (the employer's INDUSTRY/SECTOR), adapted from the UN's ISIC."
2. **How any hierarchy works** — what each level *means*, broad→specific, with a worked example showing the digits narrowing, and the rule that each level is a prefix of the next (so you roll up by truncating).
3. **Contrasts that prevent confusion** — e.g. NIC (employer's industry, "where they work") vs NCO (the person's occupation, "what they do").
4. **Domain gotchas that change the numbers** — e.g. survey weights are mandatory for population estimates (`SUM(weight)`, never `COUNT(*)`); income is proxied by consumer expenditure; multiple reference periods measure the "same" thing differently — don't mix them.
5. **Column descriptions in plain English** — "Broadest 2-digit sector code (first 2 digits of the subclass), e.g. '62' = Computer programming." not "Division label."

Also keep a **"<source> concepts in 60 seconds" primer** in `schemas/README.md`, and mirror the same conceptual explanations (compact form) into the bq-assistant `description` blocks — the LLM benefits most from understanding the domain.

Quick self-check before opening the PR: *Could a new analyst who's never heard of this survey read this file and write a correct query?* If not, the docs aren't done.

## Merge process (team rule)

- **One table at a time.** Each table lands as its own branch/PR so the data team reviews it individually. Don't batch sources/tables into one PR.
- Each external_data_sources table PR is **paired** with a bq-assistant PR adding that table's schema copy + analysis-intent block + regenerated `CLAUDE.md`.
- **Commit hygiene:** clean, professional messages — **no "Co-Authored-By: Claude" / AI-fluff trailers.** Supply git identity inline; never modify git config:
  `git -c user.name="Akshay Saxena" -c user.email="akshay@avantifellows.org" commit -m "…"`
- **No production GCS/BQ writes without an explicit go from the user.** Stage parquet for review first; load to BQ only **post-approval / post-merge.**

## BigQuery load runbook

Prereqs: dataset `avantifellows.external_data_sources` exists (`asia-south1`); the loader does NOT auto-create it. Project `avantifellows`. The clean parquet should be the **current** pipeline output, not a stale GCS copy.

1. **Regenerate, don't trust stale GCS.** Before loading, confirm the staged `gs://…/<source>/clean/*.parquet` was produced by the *current merged* pipeline. If unsure, regenerate from local clean data:
   `python load_bq.py --dry-run` → writes `/tmp/<source>_bq/<table>.parquet`. Verify columns match the schema (canonical snake_case names, no stray duplicates/dots) and row counts look right.
2. **Refresh GCS** (overwrite the stale clean parquet) so the bucket stays in sync:
   `gsutil cp /tmp/<source>_bq/*.parquet gs://avantifellows-external-data/<source>/clean/`
3. **Load each table** (idempotent WRITE_TRUNCATE), clustering fact tables on their primary filter cols:
   `bq --project_id=avantifellows load --replace --source_format=PARQUET [--clustering_fields=release_id,st] external_data_sources.<table> gs://…/<source>/clean/<table>.parquet`
   (Or run `load_bq.py` without `--dry-run` to load directly from local dataframes.)
4. **Verify:** row counts per table vs the schema's stated `rows`, and a domain sanity check (for PLFS: `SUM(weight_annual)` ≈ 1.1B per release; the all-India total reconciles).

### Load gotchas seen in the wild
- **Stale/old-vintage GCS parquets** can carry verbose or duplicate column names (e.g. `industry_division_nic_2_digit.1`). BigQuery rejects a `.` in a field name. Fix by regenerating from the current pipeline, not by patching the parquet.
- `bq load` from parquet is self-describing — no `--autodetect` needed.
- The loader keeps every clean-CSV column plus derived ones; the schema YAML is a curated **documentation subset**, so the physical table may have more columns than the YAML lists. That's expected (schemas are docs, not enforced at load).

## Accurate names (don't guess)

- GCS bucket: `gs://avantifellows-external-data` — raw: `<source>/raw/`, clean: `<source>/clean/`
- BQ dataset: `avantifellows.external_data_sources` (`asia-south1`); tables `<source>_fact_*` / `<source>_dim_*`
- Repos: `avantifellows/external_data_sources`, `avantifellows/bq-assistant`
