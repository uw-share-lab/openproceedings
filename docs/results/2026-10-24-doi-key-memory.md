# `doi_key`'s memory on a `MAX_COMPARE_LINE` value (TASK-273)

`eval/scholar_compare.py`'s `doi_key` reads every `DO` value and doi.org link in a reviewer's RIS file for
`/compare`. Until TASK-273 it unquoted a link's whole path with urllib's `unquote`, which builds a list of
fragments and holds about 20 bytes per character. At `MAX_COMPARE_LINE` that went past a file's ~250 MB budget
(`api/config.py`). `MAX_COMPARE_LINE` is 1 << 24 = 16,777,216 characters (16 MiB), the largest line an operator can
allow.

Four versions were measured ("round N" here is the Nth version of the function; review round N produced
version N+1):
- **Old**: before TASK-273 (`e8539317^`). It is the same function as the test module's `_old_doi_key`.
- **Round 1** (`e8539317`):
  - It never unquotes the trailing run.
  - It refuses a path longer than `12 * caps.MAX_DOI`.
  - It still copied the value for `strip()`, for the label's slice, for the path, and for the path reversed.
- **Round 2** (`0a5bc90a`):
  - It reads a link by position.
  - A link's one copy is its path reversed.
  - A value with no link was still sliced to its trimmed span, `rstrip`ped, and had its closing `)`s added
    back: up to three copies.
- **Now**:
  - A value with no link is read in place too. Past `caps.MAX_DOI` characters only the trailing run (`.,;)`)
    and whitespace may follow, or the key would be too long; `doi_key` checks that with position-bounded
    matches. Only the first `caps.MAX_DOI` characters are ever sliced and trimmed.
  - A link's trailing whitespace is skipped on the path's reversed copy, so `rstrip` no longer copies the
    line.

## Method

- **Inputs:** each shape is a line of about `MAX_COMPARE_LINE` characters.
- **Peak memory:** the tracemalloc peak of one call (`backend/tests/timing.py` `peak_bytes`).
- **CPU time:** one call's `time.process_time()`.
- **Machine:** an 8-core Apple Silicon Mac, Python 3.12.15, on 2026-10-24 (the last two columns on 2026-10-25).
- **Code:** the "Now" column is `eba5022f`.
- **Load:** the first pass ran at a 1-minute load average of 5-6. The pass with the "Round 2" column ran at a
  load of 16-56, so its CPU times are rough. Its peaks are not: they are counted in bytes.

## Results

A link (round 1's column is from the first pass):

| Shape | Characters | Old | Round 1 | Round 2 | Now |
|---|---|---|---|---|---|
| `https://doi.org/10.1/` + `%41` × 5,592,405 | 16,777,236 | 329.2 MB / 0.82 s | 33.6 MB / 0.09 s | 16.8 MB / 0.09 s | 16.8 MB / 0.10 s |
| `doi: ` + the same link | 16,777,241 | 346.0 MB / 0.80 s | 50.3 MB / 0.09 s | 16.8 MB / 0.10 s | 16.8 MB / 0.09 s |
| ` doi: ` + the same link + ` \n` | 16,777,244 | 362.8 MB / 0.84 s | 67.1 MB / 0.09 s | 16.8 MB / 0.09 s | 16.8 MB / 0.09 s |
| `https://doi.org/10.1/x(` + `%29` × 5,592,405 | 16,777,238 | 329.4 MB / 0.84 s | 33.6 MB / 0.28 s | 16.8 MB / 0.28 s | 16.8 MB / 0.28 s |
| `https://doi.org/10.1/x` + `%2e` × 5,592,405 | 16,777,237 | 329.2 MB / 0.81 s | 33.6 MB / 0.20 s | 16.8 MB / 0.21 s | 16.8 MB / 0.21 s |
| `https://doi.org/10.1/x` + `.` × 16,777,216 | 16,777,238 | 33.6 MB / 0.13 s | 33.6 MB / 0.32 s | 16.8 MB / 0.31 s | 16.8 MB / 0.31 s |

No link (`A` is `A` × 16,777,206; the last three rows are review-methodologist's shapes from round 2, re-measured
with the snippet below on 2026-10-25):

| Shape | Characters | Old | Round 2 | Now |
|---|---|---|---|---|
| `10.1/` + `A` | 16,777,211 | 16.8 MB / 0.12 s | under 0.1 MB / 0.01 s | under 0.1 MB / 0.00 s |
| ` 10.1/` + `A` + ` ` | 16,777,213 | 33.6 MB / 0.12 s | 16.8 MB / 0.01 s | under 0.1 MB / 0.00 s |
| `doi: 10.1/` + `A` + `.` | 16,777,217 | 33.6 MB / 0.12 s | 33.6 MB / 0.01 s | under 0.1 MB / 0.00 s |
| ` 10.1/(` + `A` + `)) ` | 16,777,216 | 50.3 MB / 0.12 s | 50.3 MB / 0.02 s | under 0.1 MB / 0.00 s |
| `10.1/` + `x` × 16,777,216 + `.` | 16,777,222 | 33.6 MB / 0.12 s | 16.8 MB / 0.01 s | under 0.1 MB / 0.00 s |
| `doi: 10.1/` + `x` × 16,777,216 + `.)` | 16,777,228 | 33.6 MB / 0.12 s | 33.6 MB / 0.01 s | under 0.1 MB / 0.00 s |
| ` 10.1/` + `x` × 16,777,216 + ` \n` | 16,777,224 | 33.6 MB / 0.11 s | 16.8 MB / 0.01 s | under 0.1 MB / 0.00 s |

**Reading:**
- **Old:** the peak was about 19.6 bytes per character on an encoded link. Each label, padding, trim or added
  `)` cost one more copy of the line.
- **Links now:** every link peaks at one copy of the line, 1.0 bytes per character for an ASCII line.
- **No link now:** a value with no link costs almost nothing. It is refused, or keyed, from its first
  `caps.MAX_DOI` characters and a scan of the rest.
- **Raw dots:** the run was already cheap before TASK-273, because it has no `%` and `unquote` returns at once.
  It now takes about 0.3 s for the reversed match, against 0.13 s before. That is linear, and well inside
  `/compare`'s time limit.

**311 MB against 329 MB.**
- TASK-273's description ("~311 MB and 2.9 s") was scaled up from the 1 MB measurement in TASK-272's review:
  19.6 MB and 169 ms of wall time, on a loaded machine. It was not measured at 1 << 24.
- The 329.2 MB here was measured at 1 << 24 characters.
- The CPU time here is 0.82 s for one call. The description's 2.9 s was wall time, scaled up from that loaded
  reading.

`test_doi_key_reads_the_largest_compare_line_in_bounded_memory` checks these bounds:
- **Under 1.1 times the line's length:** the bare, labelled, padded, `%29`-run and `%2e`-run links.
- **Under 0.1 MB (100,000 bytes):** bare, padded and labelled values with no link, one with a trailing `.`, one with an
  unbalanced `(…))`, a run of dots followed by whitespace, and the three review-methodologist shapes in the
  no-link table.

## Regenerate

```sh
d=$(mktemp -d)
git show e8539317^:backend/src/openproceedings/eval/scholar_compare.py > "$d/old.py"
git show 0a5bc90a:backend/src/openproceedings/eval/scholar_compare.py > "$d/r2.py"  # e8539317 for round 1
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

versions = (load("old", sys.argv[1]), load("r2", sys.argv[2]), doi_key)
link = "https://doi.org/10.1/" + "%41" * (N // 3)
A = "A" * (N - 10)
for v in (link, "doi: " + link, " doi: " + link + " \n", "https://doi.org/10.1/x(" + "%29" * (N // 3),
          "https://doi.org/10.1/x" + "%2e" * (N // 3), "https://doi.org/10.1/x" + "." * N,
          "10.1/" + A, " 10.1/" + A + " ", "doi: 10.1/" + A + ".", " 10.1/(" + A + ")) ",
          "10.1/" + "x" * N + ".", "doi: 10.1/" + "x" * N + ".)", " 10.1/" + "x" * N + " \n"):
    cells = []
    for f in versions:
        t = time.process_time(); f(v); dt = time.process_time() - t
        cells.append(f"{peak_bytes(lambda: f(v)) / 1e6:.1f} MB / {dt:.2f} s")
    print(f"{len(v):,}", *cells, sep=" | ")
PY
PYTHONPATH=backend uv run python "$d/mem.py" "$d/old.py" "$d/r2.py"
```
