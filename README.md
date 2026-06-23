# usgs-pipeline

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Fetch USGS earthquakes](https://github.com/tomszy91/usgs_pipeline/actions/workflows/daily_fetch.yml/badge.svg?branch=main)](https://github.com/tomszy91/usgs_pipeline/actions/workflows/daily_fetch.yml)

Daily pull from the USGS earthquake feed (magnitude >= 3.0) into a BigQuery
landing table, via GitHub Actions. Transformation and deduplication logic
lives in dbt downstream, not here.

## Setup

1. Create a BigQuery dataset (if it does not exist yet).
2. Edit `sql/create_raw_table.sql` with your real project/dataset, run it
   once in the BigQuery console.
3. Create a GCP service account with `BigQuery Data Editor` and
   `BigQuery Job User` roles on the target project. Download its JSON key.
4. In your GitHub repo settings, add these secrets:
   - `GCP_SA_KEY_B64`: output of `base64 -w 0 service-account.json`
     (on Windows PowerShell: `[Convert]::ToBase64String([IO.File]::ReadAllBytes("service-account.json"))`)
   - `BQ_PROJECT`: your GCP project id
   - `BQ_DATASET`: your BigQuery dataset name
5. Push this repo. The workflow runs daily at 06:00 UTC, or trigger it
   manually from the Actions tab (`workflow_dispatch`).

## Why magnitude >= 3.0

Global M3.0+ events average roughly 50-55 per day, with spikes to 80-90
during active aftershock sequences, comfortably under a 100/day cap.
M2.5+ regularly runs 110-140/day, which is not "occasionally over budget",
it is "usually over budget".

## What this script deliberately does NOT do

- No deduplication of repeated `event_id` values across runs (USGS updates
  magnitude/location for existing events; that is expected and handled
  in dbt via an incremental merge on `event_id`).
- No backfill / historical load. It only ever sees whatever is in the
  rolling 24h feed at run time.
- No retry logic. If a run fails, the next day's run still catches
  current data; nothing is lost except that single day's snapshot.
