# Mutation sharding recovery and the LaTeX CPU growth check

TASK-171 recovery, 2026-10-02. The initial sharding proof runs at commit
`44cd3d9839015a9ba732a8c84e08296910300648`. Its eight jobs all finished within the 140-minute
step budget, but one mutation shard and the backend suite failed. This is diagnostic evidence;
Task 171 remains open until a corrected all-eight-shard run passes.

## The timing failure and measurement method

The initial [nightly proof](https://github.com/uw-share-lab/openproceedings/actions/runs/37053299707)
failed `test_unclosed_openers_are_linear[\\(]`: 2,000 characters took 0.000808408 CPU seconds and
8,000 took 0.006696267 CPU seconds, ratio 8.283277 (cutoff `<8`). Its backend summary was
`1 failed, 6258 passed, 3 skipped in 914.31s`.

The test measured the best of nine single calls for the small text, then independently the best of
nine for the large text. Thread CPU time excludes preemption, but CPU frequency and allocation cost
can vary between those two phases. The original method passed locally (ratios 3.994221, 4.066374,
4.279078); the exact host condition that caused the CI outlier cannot be recovered from its log.

The revised test warms both sizes, batches eight calls per timing sample, pairs small and large
samples in nine rounds, reverses their order every other round, and compares the median of the nine
paired ratios. Allocation and garbage collection stay included. The three input shapes, 2,000/8,000
character lengths, `<8` growth cutoff and 1 second query-cap CPU budget are unchanged.

Measurements below ran serially under the shared `heavy.sh` lock after the performance report finished.
Small and large times are medians of per-call thread CPU seconds; the growth column is the median of
paired ratios, which need not equal the ratio of those two medians.

| Behavior            | Opener | Small CPU seconds | Large CPU seconds | Paired growth |
| ------------------- | ------ | ----------------: | ----------------: | ------------: |
| Current tokenizer   | `$1`   |       0.001863104 |       0.007578891 |      4.049418 |
| Current tokenizer   | `\(`   |       0.000656542 |       0.002660312 |      4.052738 |
| Current tokenizer   | `\[`   |       0.000659396 |       0.002680427 |      4.043592 |
| Former closer scans | `$1`   |       0.107690010 |       1.727189833 |     16.023047 |
| Former closer scans | `\(`   |       0.050667875 |       0.806977938 |     16.016399 |
| Former closer scans | `\[`   |       0.050625766 |       0.805162344 |     15.903574 |

Every former-scan row invoked the actual edited test and failed its growth assertion. The negative
control restores the old repeated scan behavior using the same `_find` and `_find_closing_dollar`
functions that the `_Closers` property checks as its semantic oracle. The rest of the current tokenizer
is retained; no production source, clock, threshold or output expectation is patched.
Raw investigation evidence: `/tmp/latex-timing-investigate.log`.

Reproduce the negative control from the repository root (`uv run python` in a heredoc):

```python
import importlib.util
from pathlib import Path
import openproceedings.query.normalize as norm

class Scans:
    def __init__(self, text):
        self.text = text
    def find(self, start, closer):
        return norm._find(self.text, start, closer)
    def dollar(self, start):
        return norm._find_closing_dollar(self.text, start)

spec = importlib.util.spec_from_file_location(
    "latex_scan_test", Path("backend/tests/unit/test_latex_scan.py")
)
test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test)
norm._Closers = Scans
for unit in ("$1", "\\(", "\\["):
    try:
        test.test_unclosed_openers_are_linear(unit)
    except AssertionError as error:
        print("expected growth failure:", error)
    else:
        raise AssertionError(f"quadratic scan survived for {unit!r}")
```

## Controlled sampling-method reproduction

A phase-drift model makes the real tokenizer do two extra identical calls after its ninth invocation,
modeling a threefold throughput slowdown without mocking any clock. With a fresh model for each
method, the original consecutive independent minima reported 12.515577 for the linear `\(` input;
the warmed alternating eight-call batches reported 4.063655. Both use the unchanged `<8` boundary.
The first paired round straddles the modeled transition, and the median retains the steady behavior
of the other rounds. This demonstrates the estimator's susceptibility to temporal drift, not the
specific host cause of the CI outlier. Evidence: `/tmp/latex-timing-focused.log` and
`/tmp/latex-phase-drift.py`.

## Local table portability finding

The first recovery `make tooling` failed the existing stable-shard row in
`test-mutate-shard.sh` on stock macOS Bash 3.2.57: the `case` expression inside `$(...)` was parsed as
ending at the pattern's `)`, yielding a command-substitution syntax error and 32 passed/1 failed.
The fix computes the same nonempty/nonerror condition with `case` outside the substitution and passes
its result to the same assertion. It adds no exception or weaker expectation. Source and red evidence:
`/tmp/latex-timing-focused.log`. The focused table rerun passed all 33 rows on Bash 3.2.57 and Bash 5.3.9; ShellCheck passed. The full `make tooling` rerun passed, including 774 gate rows and all 33 sharding rows (`/tmp/mutation-tooling-recovery.log`).

## Local timing verification

`uv run pytest backend/tests/unit/test_latex_scan.py -q --hypothesis-profile=ci`:
`4 passed in 2.15s`. Twenty repetitions of the actual growth test for each of its three shapes also
passed: 60 checks, 28.047281416 thread CPU seconds. `make lint` passed. These ran serially under
`heavy.sh`, with Node 22.23.3 and `PYTEST_XDIST_AUTO_NUM_WORKERS=4`.
The full integration gate is deferred until the merged hooks fix is integrated; no full-suite or
corrected GitHub proof pass is claimed here.

## Initial mutation proof

Run 37053299707 start-to-completion durations, from the GitHub jobs response saved in
`/tmp/mutation-sharding-initial-proof.json`:

| Shard | Result  | Duration |
| ----- | ------- | -------- |
| 1/8   | success | 1:04:07  |
| 2/8   | success | 0:53:47  |
| 3/8   | success | 1:21:14  |
| 4/8   | success | 1:21:00  |
| 5/8   | success | 1:21:44  |
| 6/8   | failure | 1:21:15  |
| 7/8   | success | 1:20:08  |
| 8/8   | success | 1:19:09  |

Shard 6 retained `protect-data-dir: worktree paths compared case-sensitively`, because its casefold
coverage skipped Linux. The hooks recovery owns the deterministic Linux coverage fix. The survivor
remains a real failure; it is not marked equivalent. Corrected proof and final gate results are pending
integration of that fix.

## Complete corrected nightly proof — 2026-10-03

[Run37115476175](https://github.com/uw-share-lab/openproceedings/actions/runs/37115476175), attempt1, tested exact source `8d273d6118f410857c8098ca01678ecf466d12f2` on `chore/task-171-mutation-final`. All27 jobs completed successfully, including suite-ci, all property/year-edit/differential jobs and benchmarks. The collector returned PASS with no problems; actual logs/metadata/ordered exact-source partitions are preserved in `/tmp/task171-unicode-proof-37115476175-final` and manifest `/tmp/task171-unicode-proof-manifest/manifest.json`.

| Shard | Mutants | Job min:sec | Mutation step min:sec | Result |
| --- | ---: | ---: | ---: | --- |
| 1/8 | 97 | 122:46 | 122:38 | success / 0 problems |
| 2/8 | 97 | 121:10 | 120:59 | success / 0 problems |
| 3/8 | 97 | 93:42 | 93:34 | success / 0 problems |
| 4/8 | 97 | 122:04 | 121:54 | success / 0 problems |
| 5/8 | 97 | 120:47 | 120:37 | success / 0 problems |
| 6/8 | 96 | 122:37 | 122:30 | success / 0 problems |
| 7/8 | 96 | 120:28 | 120:17 | success / 0 problems |
| 8/8 | 96 | 123:59 | 123:47 | success / 0 problems |

All773 complete row labels match the immutable source partition in order. Every shard has zero unexpected survivors/stale patterns; documented equivalent survivors retain the audited annotations. Job and mutation-step durations stay below150 and140minutes respectively, with headroom under the original6hour GitHub cap. Effective exit0 follows from successful mutation steps plus complete zero-problem summaries; GitHub does not print a separate successful process exit code. These are actual results, not predictions from earlier partial runs. The actual nightly suite-ci summary is6752passed4skipped in807.55s; benchmark job72passed2skipped in31.60s. These remote summaries are distinct from the local full-test totals.

Merged hooks fixed the initial Linuxcasefold survivor. Integration also required controlled shard outputs captured before assertion calls to satisfy the merged probe linter without exemptions. Run37112111841 then exposed a property-fixture Unicode seed crash before any production assertion; an explicit surrogate example and surrogatepass seed fixed it while preserving arbitraryUnicode and canonical checks. That failed run remains historical evidence, not completion proof. Source8d273 local full test/lint/tooling passed (6757backend,3skips;4724frontend in41files;870hook and118tooling cases). Official14runner mutations passed at2a39; runner/mutant definitions are identical at8d273.

This closure changes only task metadata, results and dated learning. Its commit does not claim the nightly ran on the later closure SHA: proof remains pinned to source8d273. Fresh closing full test/lint/tooling and independent exact-head review are required before publication.
