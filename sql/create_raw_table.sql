-- Run once manually before the first GitHub Actions run.
-- Partitioning by ingested_at keeps daily appends cheap to query
-- and gives dbt an easy filter for incremental runs.

CREATE TABLE IF NOT EXISTS `your_project.your_dataset.raw_earthquakes` (
  event_id STRING,
  event_time TIMESTAMP,
  updated_at TIMESTAMP,
  magnitude FLOAT64,
  place STRING,
  longitude FLOAT64,
  latitude FLOAT64,
  depth_km FLOAT64,
  status STRING,
  ingested_at TIMESTAMP,
  raw_json STRING
)
PARTITION BY DATE(ingested_at);
