# ADR-015: Knowledge graph type inheritance and Activity nodes

## Status

Accepted for the CSV-backed prototype.

## Context

The initial ontology repeated concrete place types in relationship contracts and
could not distinguish shared properties from subtype-specific properties. It
also represented activities such as cloud hunting or trying egg coffee only as
free text.

## Decision

- Keep `nodes` as the allowlist of concrete entity types.
- Declare `Entity`, `LocationEntity`, `Place`, and `AdministrativeArea` in
  `abstract_nodes`; persisted entities cannot use these types.
- Use `node_type_definitions.<type>.extends` for single inheritance.
- Inherit required and optional property keys from ancestors. Every persisted
  property value retains its own source.
- Add concrete `Activity` nodes and `OFFERS_ACTIVITY` edges from `Place` to
  `Activity`.
- Allow `RECOMMENDS` to target either `Place` descendants or `Activity`.
- Keep edge `recommendations` as a structured JSON array. ADR-016 supersedes
  the node-level `recommend` property with `special_experience`.

## Consequences

Relationship validation resolves the full type lineage, so an ontology contract
using `Place` accepts `TravelPlace`, `Restaurant`, `DrinkDessert`, and
`Accommodation`. Admin and AI-import validation report inherited required
properties. Import scripts read the concrete node allowlist from `schema.yaml`
instead of treating parent types as persisted entity types.
