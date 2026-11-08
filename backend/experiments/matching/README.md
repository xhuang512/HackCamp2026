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

## Phase 2: controlled similarity ablation

Phase 1 compared algorithms that differed in both feasibility and member
selection. Phase 2 answers a narrower question: when availability handling is
held constant, does attribute-aware selection improve the score it targets?

### Method

`feasible_greedy` is the controlled baseline. It inherits the exact matching
loop used by `similarity_greedy`, including:

- the 30-minute minimum and 15-minute candidate grid;
- candidate-window and coverage-first ordering;
- group-size partitioning and constrained-student anchor;
- maximal common meeting intervals and the shared validator;
- newcomer/flexibility/ID tie-breaking.

Its only difference is companion selection: `feasible_greedy` uses the shared
deterministic tie-breaks, while `similarity_greedy` ranks feasible companions by
weighted attribute similarity before applying those same tie-breaks.

The recorded Phase 2 matrix uses populations of 100, 500, and 2,000, seeds 17,
41, and 73, and medium-overlap schedules. For each size/seed pair, one schedule
population is reused unchanged across four attribute configurations:

- **strong clustered:** original latent course/interest communities;
- **weakly correlated:** half of every feature's student profile bundles are
  independently permuted;
- **permuted:** every feature's bundles are independently permuted;
- **sparse:** 60% of profiles are fully missing, then each remaining value has
  a 35% retention probability.

Weak and full permutations preserve exact per-value frequencies. IDs,
availability, newcomer status, and hangout counts never change between variants.
There are 36 paired datasets per strategy. Coverage, newcomer coverage, group
counts, group sizes, and constraint checks use the same evaluation functions.
The complete rows and per-seed differences are in `ablation_results.json`,
`ablation_results.csv`, and `ablation_paired.csv`; Phase 1 artifacts remain
unchanged.

Run the ablation from `backend/`:

```bash
.venv/bin/python -m experiments.matching.ablation
```

### Four-strategy results

Values below are means across the four attribute profiles and three seeds at
each population size. Groups are valid groups; `3/4/5` is their mean size
distribution. Production violations are groups rejected by the experiment's
30-minute contract.

| Strategy | N | Coverage | Similarity | Newcomer coverage | Groups (3/4/5) | Runtime | Violations |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Production greedy | 100 | 62.48% | 0.1870 | 58.75% | 51 (5/3.3/42.7) | 0.011s | 344 |
| Feasible greedy | 100 | 97.67% | 0.1903 | 98.39% | 85 (17/13/55) | 0.005s | 0 |
| Similarity greedy | 100 | 97.67% | 0.2481 | 98.39% | 85 (17/13/55) | 0.032s | 0 |
| Similarity + local search | 100 | 97.67% | 0.2535 | 98.39% | 85 (17.3/12.5/55.3) | 0.333s | 0 |
| Production greedy | 500 | 78.43% | 0.1890 | 79.43% | 300.3 (6.7/4.7/289) | 0.296s | 960 |
| Feasible greedy | 500 | 99.96% | 0.1940 | 99.94% | 392 (27.7/14/350.3) | 0.044s | 0 |
| Similarity greedy | 500 | 99.96% | 0.3220 | 99.94% | 392 (27.7/14/350.3) | 0.893s | 0 |
| Similarity + local search | 500 | 99.96% | 0.3226 | 99.94% | 392 (26.8/15.7/349.5) | 1.169s | 0 |
| Production greedy | 2,000 | 83.20% | 0.1898 | 82.71% | 1,263.7 (7.7/4.7/1,251.3) | 4.844s | 3,032 |
| Feasible greedy | 2,000 | 100.00% | 0.1931 | 100.00% | 1,528 (27/15.7/1,485.3) | 0.884s | 0 |
| Similarity greedy | 2,000 | 100.00% | 0.3892 | 100.00% | 1,528 (27/15.7/1,485.3) | 10.890s | 0 |
| Similarity + local search | 2,000 | 100.00% | 0.3893 | 100.00% | 1,528 (27/15.7/1,485.3) | 12.078s | 0 |

The production baseline remains useful context, but it is not the causal
similarity comparison. Its lower *valid* coverage primarily reflects the
30-minute rule it does not implement. The controlled comparison is feasible
greedy versus similarity greedy.

### Paired controlled results

Similarity greedy and feasible greedy had identical coverage, newcomer
coverage, valid-group count, and group-size distribution in all 36 paired
datasets. Similarity never regressed. Across all cases, its mean absolute
similarity gain was `0.1273`; pooled mean similarity rose from `0.1925` to
`0.3198`. The mean runtime increase was `3.63s`, but pooled ratios are misleading
because feasible greedy is extremely fast at N=100.

| N | Attribute profile | Absolute similarity gain | SD across seeds | Relative gain | Coverage change |
| ---: | --- | ---: | ---: | ---: | ---: |
| 100 | Strong clustered | 0.0754 | 0.0016 | 29.5% | 0 |
| 100 | Weakly correlated | 0.0688 | 0.0120 | 27.9% | 0 |
| 100 | Permuted | 0.0723 | 0.0077 | 29.2% | 0 |
| 100 | Sparse | 0.0148 | 0.0019 | 158.0% | 0 |
| 500 | Strong clustered | 0.1625 | 0.0016 | 61.9% | 0 |
| 500 | Weakly correlated | 0.1499 | 0.0025 | 59.0% | 0 |
| 500 | Permuted | 0.1533 | 0.0033 | 61.5% | 0 |
| 500 | Sparse | 0.0465 | 0.0052 | 473.5% | 0 |
| 2,000 | Strong clustered | 0.2483 | 0.0013 | 94.9% | 0 |
| 2,000 | Weakly correlated | 0.2257 | 0.0020 | 89.1% | 0 |
| 2,000 | Permuted | 0.2290 | 0.0027 | 91.8% | 0 |
| 2,000 | Sparse | 0.0813 | 0.0008 | 1,006.3% | 0 |

Sparse relative gains are large only because its feasible-baseline similarity
is near zero (`0.008–0.010`). Absolute gains are the meaningful quantity there,
and they are much smaller than in information-rich profiles. Full permutation
breaks cross-feature/student correlations but leaves individual feature
frequencies and repeated values intact, so a token-overlap optimizer can still
improve its own metric. This is not evidence that the permuted groups are more
socially compatible.

### Local-search objective review

The local-search objective matches the reported metric. Each group score is
mean pairwise similarity; local search sums those group scores, while evaluation
reports their mean. Swaps and reassignments preserve group count, so the sum and
mean have identical ordering. Tests also verify that the exact matched
student-weekday set is preserved.

Local search improved similarity in all 36 cases without any coverage loss, but
the mean absolute gain over similarity greedy was only `0.0020` (`1.67%`
relative). By size, the gain fell from `0.00540` at N=100 to `0.00061` at N=500
and `0.000045` at N=2,000. Mean runtime overheads were `0.300s`, `0.276s`, and
`1.188s`, respectively. Some individual runtime deltas were negative because
each strategy was timed once per dataset and short runs are noisy; quality and
coverage comparisons are deterministic.

Newcomer handling is **not** an explicit optimization objective. Lower hangout
count is only a deterministic tie-break after feasibility (and, for the
similarity strategy, after similarity). That explains why controlled newcomer
coverage is identical; this study must not be cited as evidence for a dedicated
newcomer-priority policy.

### Runtime profile

A standard-library `cProfile` run on one 500-student strong-clustered case
recorded 24.5 million calls in 7.15 instrumented seconds. Repeated
`pair_similarity` calls consumed 4.50 seconds cumulatively (351,796 calls),
including 1.85 seconds repeatedly normalizing weights that were already
normalized. Slot-index construction used 0.05 seconds and repeated best-slot
selection used 0.12 seconds. Pairwise scoring, not candidate generation, is the
clear dominant operation in this implementation. No performance optimization
was made in Phase 2; caching pair scores and normalized weights should be
measured before any production proposal.

### Recommendation and limitations

**Research answer:** yes. On these synthetic datasets, Tags, Courses,
Languages, and Interests measurably improve the exact group-similarity metric
when feasibility, candidate generation, group sizes, and coverage priority are
held constant. The controlled gain occurred in every measured case without a
coverage regression.

This supports considering similarity greedy for a production prototype, but
does not yet justify deploying it as the default. The metric is built from the
same attributes the algorithm directly optimizes, so improvement is partly
mechanical. Synthetic token overlap does not demonstrate friendship, safety,
attendance, or meetup success. Attribute distributions may overstate repeated
signals, missingness may not resemble real onboarding, and only medium-overlap
schedules were used in this controlled phase. At 2,000 students, roughly
11-second greedy runtime also needs a product-specific latency assessment.

The bounded local search is not recommended for an initial production version:
its measured quality gain is tiny at larger populations relative to its added
complexity and runtime. A reasonable next step is an offline replay or opt-in
pilot with privacy-reviewed, consented outcome measures, plus pair-score caching
benchmarks—not direct production integration from synthetic results alone.

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
