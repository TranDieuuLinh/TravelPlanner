# ADR-030: Cluster-first capacity preflight before AI planning

- Status: Accepted
- Date: 2026-08-07

## Context

An unlocked URL trip previously ran the complete ThemePlanner and PlaceSelector
workflow again whenever resolved source places overflowed. A 3-day request could
therefore execute separate 3, 4, 5, and 6-day plans. The attempts repeated LLM,
catalog, Finder, and routing work even though Explorer had already resolved the
same mandatory places.

Day themes also made trip-wide experience requirements depend on the selected
duration. Changing only the day count could consequently regenerate otherwise
identical theme research.

## Decision

Run a deterministic `ClusterFirstRepairSolver` after Explorer identity
resolution and before ThemePlanner:

1. hydrate resolved source places into a mandatory candidate pool;
2. build one capacity-preflight matrix, using the configured provider when every
   candidate has coordinates and a geodesic/default-time fallback otherwise;
3. allocate mandatory activities and the three daily meal capacities by greedy
   geographic insertion;
4. open additional days in memory only when duration is unlocked;
5. keep overflow unscheduled when duration is locked;
6. write the chosen day back as an internal source-day allocation; and
7. invoke ThemePlanner and PlaceSelector exactly once.

ThemePlanner returns trip-wide signals and required-experience candidates. It no
longer derives their minimum count or capacity from the number of trip days.
New Plan API snapshots omit `PlanDay.theme`; the backend still accepts that
field while loading older revisions.

The preflight matrix and the final route matrix are reported separately. The
route matrix can contain required-experience, Finder, and meal candidates that
do not exist at preflight time. Moving all candidate discovery ahead of a single
expandable global matrix is a later cutover and must not be claimed as current
behavior.

## Consequences

- Unlocked trips do not rerun the LLM and PlaceSelector for successive day
  counts.
- Fixed-duration overflow remains visible in `UnscheduledPlace`.
- `needs_review` candidates never enter automatic scheduling and remain visible
  even when they have no `topMatches`.
- Allocation is deterministic and testable without an LLM.
- V1 is bounded greedy plus one move-repair pass; Beam Search and CP-SAT are not
  required for the current production boundary.
