# `doi_key`'s memory on a percent-encoded doi.org link (TASK-273)

`eval/scholar_compare.py`'s `doi_key` reads every `DO` value and doi.org link of a reviewer's RIS file in
`/compare`. Until TASK-273 it unquoted a link's whole path with urllib's `unquote`, which builds a list of
fragments and holds about 20 bytes per character. At `MAX_COMPARE_LINE` (1 << 24 = 16,777,216 characters, the
largest line an operator can allow) that went past a file's ~250 MB budget (`api/config.py`).

Three versions were measured:
- **Old**: before TASK-273 (`e8539317^`, the same function as the test module's `_old_doi_key`).
- **Round 1**: `e8539317`. It never unquotes the trailing run, and refuses a path longer than
  `12 * caps.MAX_DOI`. But it still copied the value for `strip()`, for the label's slice, for the path, and
  for the path reversed.
- **Now**: the value is read by position. The only copy of a long value is the link's path reversed.
  `rstrip`'s copy is made only when there is trailing whitespace, and it is freed before the reversal.

## Method

Each shape is a line of `MAX_COMPARE_LINE` characters, give or take its prefix. The peak is the tracemalloc
peak of one call (`backend/tests/timing.py` `peak_bytes`). CPU time is one call's `time.process_time()`.
Measured on 2026-10-24 on an 8-core Apple Silicon Mac (Python 3.12.15) at `56adca97` plus the working tree,
with a 1-minute load average of 5-6.

## Results

| Shape | Characters | Old | Round 1 | Now |
|---|---|---|---|---|
| `https://doi.org/10.1/` + `%41` × 5,592,405 | 16,777,236 | 329.2 MB / 0.82 s | 33.6 MB / 0.09 s | 16.8 MB / 0.09 s |
| `doi: ` + the same link | 16,777,241 | 346.0 MB / 0.80 s | 50.3 MB / 0.09 s | 16.8 MB / 0.09 s |
| ` doi: ` + the same link + ` \n` | 16,777,244 | 362.8 MB / 0.84 s | 67.1 MB / 0.09 s | 16.8 MB / 0.09 s |
| `https://doi.org/10.1/x(` + `%29` × 5,592,405 | 16,777,238 | 329.4 MB / 0.84 s | 33.6 MB / 0.28 s | 16.8 MB / 0.29 s |
| `https://doi.org/10.1/x` + `%2e` × 5,592,405 | 16,777,237 | 329.2 MB / 0.81 s | 33.6 MB / 0.20 s | 16.8 MB / 0.20 s |
| `https://doi.org/10.1/x` + `.` × 16,777,216 | 16,777,238 | 33.6 MB / 0.13 s | 33.6 MB / 0.32 s | 16.8 MB / 0.31 s |

**Reading:**
- The old function's peak was about 19.6 bytes per character, plus one more copy of the line for each of a
  label and padding.
- Now every shape peaks at one copy of the line: 1.0 bytes per character for an ASCII line.
- The raw-dots run was already cheap, because it has no `%` and `unquote` returns at once. It now takes about
  0.3 s for the reversed match, against 0.13 s before. That is linear, and well inside `/compare`'s time limit.

**311 MB against 329 MB.** TASK-273's description ("~311 MB and 2.9 s") scaled the 1 MB measurement found in
TASK-272's review (19.6 MB, 169 ms of wall time on a loaded machine). It was not a measurement at 1 << 24.
The 329.2 MB here was measured at 1 << 24 characters. The CPU time here is 0.82 s for one call; the description's
2.9 s was wall time scaled up from a loaded reading.

`test_doi_key_reads_the_largest_compare_line_in_bounded_memory` holds the bare, labelled, padded,
`%29`-run and `%2e`-run shapes at under 1.1 times the line's length.

## Regenerate

```sh
d=$(mktemp -d)
git show e8539317^:backend/src/openproceedings/eval/scholar_compare.py > "$d/old.py"
git show e8539317:backend/src/openproceedings/eval/scholar_compare.py > "$d/r1.py"
cat > "$d/mem.py" <<'PY'
import importlib.util, sys, time
from tests.timing import peak_bytes
from openproceedings.api.config import MAX_COMPARE_LINE as N
from openproceedings.eval.scholar_compare import doi_key

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # its dataclasses look their module up
    spec.loader.exec_module(mod)
    return mod.doi_key

versions = (load("old", sys.argv[1]), load("r1", sys.argv[2]), doi_key)
link = "https://doi.org/10.1/" + "%41" * (N // 3)
for v in (link, "doi: " + link, " doi: " + link + " \n", "https://doi.org/10.1/x(" + "%29" * (N // 3),
          "https://doi.org/10.1/x" + "%2e" * (N // 3), "https://doi.org/10.1/x" + "." * N):
    cells = []
    for f in versions:
        t = time.process_time(); f(v); dt = time.process_time() - t
        cells.append(f"{peak_bytes(lambda: f(v)) / 1e6:.1f} MB / {dt:.2f} s")
    print(f"{len(v):,}", *cells, sep=" | ")
PY
PYTHONPATH=backend uv run python "$d/mem.py" "$d/old.py" "$d/r1.py"
```
