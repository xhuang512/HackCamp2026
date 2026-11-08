# Offline similarity-aware matching experiment

This package compares three group-forming strategies on deterministic synthetic
students. It is deliberately separate from FastAPI, repositories, Supabase, and
the production matching path. It reads no environment variables and makes no
network calls.

## What is being compared

1. `production_greedy` calls the existing `app.engine.form_groups()` directly.
   The adapter does not repair or reinterpret its output. The production engine
   accepts any non-empty overlap, so groups with less than the experiment's
   30-minute minimum are reported as hard-constraint violations and excluded
   from valid coverage and similarity metrics.
2. `similarity_greedy` constructs only feasible groups. It first chooses the
   30-minute availability slot that covers the most currently unmatched
   student-weekday opportunities, then uses similarity to select companions
   within that feasible pool. Deterministic IDs break score ties.
3. `similarity_local_search` starts from the similarity greedy result and makes
   bounded swaps or 4/4-to-3/5 reassignments. Every move preserves the matched
   population, group sizes, uniqueness, and the fixed meeting intervals. A move
   is accepted only when mean pairwise similarity improves.

The optimization order is lexicographic:

1. satisfy hard feasibility;
2. preserve or improve coverage;
3. improve soft similarity.

The experiment does **not** claim the similarity strategies are better unless
the generated result files show improved similarity without lower valid
coverage on the same dataset.

## Data and assumptions

All data is synthetic. Each student has an ID, weekly availability, tags,
courses, languages, interests, newcomer status, and prior hangout count. The
generator uses non-uniform timetable peaks and latent attribute communities.
`low`, `medium`, and `high` overlap profiles vary schedule concentration;
`clustered` and `dispersed` profiles vary attribute correlation.

A weekday is one evaluation window. A student may be matched once on Monday and
again on Tuesday, but never twice on the same weekday. A valid group:

- contains 3–5 distinct students;
- has a concrete common interval of at least 30 minutes covered by every member;
- contains no student already assigned in that weekday window.

Availability is a hard constraint and is not part of the similarity score.
For attribute set \(A_f\) and \(B_f\), feature similarity is weighted Jaccard:

```text
J_f(A, B) = |A_f intersect B_f| / |A_f union B_f|
pair(A, B) = sum(normalized_weight_f * J_f(A, B))
```

Two empty (or missing) sets score `0`, not `1`. Group quality is the mean score
over every member pair. Default weights are tags `0.25`, courses `0.30`,
languages `0.20`, and interests `0.25`; weights must be finite, non-negative,
and are normalized to sum to one.

Coverage uses *feasible student-weekday opportunities* as its denominator: a
student-day belongs to the denominator when that student participates in at
least one 30-minute slot containing three or more students. This avoids calling
an isolated schedule "unmatched" when no valid group was possible.

## Reproduce

From `backend/`, run the unit tests:

```bash
.venv/bin/python -m pytest tests/test_matching_experiment.py
```

Run the full experiment (100, 500, and 2,000 students; three seeds; all overlap
and attribute profiles):

```bash
.venv/bin/python -m experiments.matching.evaluate
```

For a quick smoke run:

```bash
.venv/bin/python -m experiments.matching.evaluate \
  --sizes 100 --seeds 17 \
  --overlaps medium --attributes clustered \
  --json-output experiments/matching/results-smoke.json \
  --csv-output experiments/matching/results-smoke.csv
```

The command prints a terminal table and writes machine-readable JSON and CSV.
Every row records the seed, profiles, match rate, unmatched count, similarity,
group-size distribution, newcomer coverage, runtime, and hard violations. JSON
also contains means and sample standard deviations across seeds.

## Recorded findings

The committed `results.json` and `results.csv` were produced with the full
default matrix: 100, 500, and 2,000 students; seeds 17, 41, and 73; every
overlap profile; and both attribute profiles (54 datasets per strategy). On the
machine that generated them:

| Strategy | Mean valid match rate | Mean similarity | Mean newcomer coverage | Mean runtime | Hard violations |
| --- | ---: | ---: | ---: | ---: | ---: |
| Production greedy | 78.31% | 0.2484 | 78.03% | 1.791 s | 5,185 |
| Similarity greedy | 99.02% | 0.4073 | 99.13% | 4.956 s | 0 |
| Similarity local search | 99.02% | 0.4093 | 99.13% | 5.449 s | 0 |

For this synthetic matrix, the local search preserved greedy coverage in all
54 cases and improved mean similarity in all 54, with no hard-constraint
regression. Its average absolute similarity gain was small (`0.0020`) for an
average runtime increase of about `0.49 s`. The larger gain relative to the
production baseline combines two effects: similarity ranking and enforcement
of the experiment's 30-minute minimum. The production engine is not invalid for
its current application contract—it simply has no 30-minute rule—so its 5,185
reported violations should be read as a contract difference, not a production
bug.

These findings apply only to the synthetic distributions and seeds above. They
do not establish real-world outcome quality or justify production integration.

## Limitations

- Weekly free blocks are synthetic abstractions, not class schedules.
- The greedy candidate grid advances in 15-minute steps and also checks each
  interval's last possible 30-minute start.
- Similarity is exact-token Jaccard; it does not understand semantic closeness.
- Newcomer data is measured and used as a deterministic tie-breaker, not as an
  objective that can override coverage or similarity.
- Local search is bounded and deterministic, so it may stop before a global
  optimum. Runtime depends on the configured operation budget.
- The baseline comparison reflects the current production engine at execution
  time; importing it is intentional, but no experiment code is used by the app.
