# ADR-016: Special experience contract for Knowledge Graph nodes

## Status

Accepted for the CSV-backed prototype.

## Context

The generic node property `recommend` did not communicate whether a value was
an itinerary tip, a standout experience, or a must-try suggestion. Edges already
use the distinct `recommendations` column and should keep that stable contract.

## Decision

- Rename node property `recommend` to `special_experience`.
- Populate it by default for Place and Activity nodes, not structural Area nodes.
- Increment the Knowledge Graph schema to version 4.
- Keep `special_experience` and edge `recommendations` as JSON arrays whose
  items may contain `intent`, `priority`, `timeSlots`, `recommendedItems`, and
  `reason`.
- Use `must` only when a deterministic popularity/taxonomy rule supports it;
  otherwise use `recommended` or `optional`.
- Taxonomy-derived time slots are broad planning suggestions, not externally
  verified opening hours. Their property provenance must identify inference.
- Keep the edge CSV column name `recommendations` for compatibility.
- Keep `LOCATED_IN` and `PART_OF` recommendations empty; contextual guidance
  belongs to experience-bearing edges such as `OFFERS_ACTIVITY`.

## Consequences

Admin validation and rendering use `special_experience` for node-level cards.
Existing datasets and test fixtures must migrate the old property key. Planner
consumers can distinguish a node's standout experience from the contextual
recommendation attached to an edge.
