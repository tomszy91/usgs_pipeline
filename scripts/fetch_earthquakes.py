"""
fetch_earthquakes.py

Pulls earthquake events (magnitude >= MIN_MAGNITUDE) from the USGS
2.5_day GeoJSON feed and appends them to a BigQuery landing table.

Design decision: this script does ONE thing, fetch + append.
No deduplication, no "latest version per event" logic here.
That logic lives downstream in dbt (incremental model, merge
strategy on event_id), because USGS updates magnitude/location
for existing events after the fact (see the `updated` field).
Every row gets its own `ingested_at` timestamp so dbt can tell
which fetch run produced it, independent of USGS's own `updated`.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

import requests
from google.cloud import bigquery

START_DATE_RAW = datetime.now(timezone.utc) - timedelta(days=1)
START_DATE = START_DATE_RAW.strftime("%Y-%m-%d") + "T06:00:00"
MIN_MAGNITUDE = 3.0
USGS_FEED_URL = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime={START_DATE}&minmagnitude={MIN_MAGNITUDE}"

BQ_PROJECT = os.environ["BQ_PROJECT"]
BQ_DATASET = os.environ["BQ_DATASET"]
BQ_TABLE = os.environ.get("BQ_TABLE", "raw_earthquakes")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def fetch_features() -> list[dict]:
    response = requests.get(USGS_FEED_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return payload.get("features", [])


def to_bq_row(feature: dict, ingested_at: str):
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})
    coords = geom.get("coordinates") or [None, None, None]

    magnitude = props.get("mag")
    if magnitude is None or magnitude < MIN_MAGNITUDE:
        return None

    return {
        "event_id": feature.get("id"),
        "event_time": _epoch_ms_to_iso(props.get("time")),
        "updated_at": _epoch_ms_to_iso(props.get("updated")),
        "magnitude": magnitude,
        "place": props.get("place"),
        "longitude": coords[0],
        "latitude": coords[1],
        "depth_km": coords[2],
        "status": props.get("status"),
        "ingested_at": ingested_at,
        "raw_json": json.dumps(feature),
    }


def _epoch_ms_to_iso(epoch_ms):
    if epoch_ms is None:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).isoformat()


def load_to_bigquery(rows: list[dict]) -> None:
    if not rows:
        logger.info("No rows above MIN_MAGNITUDE=%s, nothing to load.", MIN_MAGNITUDE)
        return

    client = bigquery.Client(project=BQ_PROJECT)
    table_ref = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=[
            bigquery.SchemaField("event_id", "STRING"),
            bigquery.SchemaField("event_time", "TIMESTAMP"),
            bigquery.SchemaField("updated_at", "TIMESTAMP"),
            bigquery.SchemaField("magnitude", "FLOAT64"),
            bigquery.SchemaField("place", "STRING"),
            bigquery.SchemaField("longitude", "FLOAT64"),
            bigquery.SchemaField("latitude", "FLOAT64"),
            bigquery.SchemaField("depth_km", "FLOAT64"),
            bigquery.SchemaField("status", "STRING"),
            bigquery.SchemaField("ingested_at", "TIMESTAMP"),
            bigquery.SchemaField("raw_json", "STRING"),
        ],
    )

    load_job = client.load_table_from_json(rows, table_ref, job_config=job_config)
    load_job.result()  # wait for completion, raises on error

    logger.info("Loaded %d rows into %s", len(rows), table_ref)


def main():
    ingested_at = datetime.now(timezone.utc).isoformat()

    features = fetch_features()
    logger.info("Fetched %d raw features from USGS feed", len(features))

    rows = []
    for feature in features:
        row = to_bq_row(feature, ingested_at)
        if row is not None:
            rows.append(row)

    logger.info("Kept %d rows with magnitude >= %s", len(rows), MIN_MAGNITUDE)
    load_to_bigquery(rows)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Fetch job failed")
        sys.exit(1)
