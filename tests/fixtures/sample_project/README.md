# Sample Project

This is a test project for projMap.

## Architecture Decision

We decided to use DuckDB as the primary storage engine because it provides
embedded SQL with good performance for analytical workloads.

## Known Risk

The current approach depends on Anthropic API availability, which creates
a single point of failure for extraction.

## Assumptions

We assume all project documentation is in English.
