# Handoff Notes

## Decision History

The team decided to skip LanceDB in Phase 1 because embedding search is not
required for the MVP decision graph extraction.

This supersedes the earlier plan to use LanceDB for vector storage.

## Risk

If the project grows beyond 1000 nodes, DuckDB may need indexing optimization.
