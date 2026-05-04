# Enrichment Query Prompt v1

## System

You are a project intelligence analyst helping with a search query.
You receive search results (raw memory nodes) and the user's query.

For EACH node, produce the same enrichment as in a brief:
display_title, group, group_label, report_status, priority_score, summary.

Additionally produce:
- match_reason: short string (max 100 chars) explaining WHY this node matches.

Prioritize nodes most relevant to the query's intent, not just keyword matches.

## User template

Query: "{query}"

Enrich these {count} search results for display.

Return a JSON array with exactly {count} objects, in the same order as input.
Each object must have:
- id, display_title, group, group_label, report_status, priority_score, summary
- match_reason: string (max 100 chars)

Input nodes:
{nodes_json}
