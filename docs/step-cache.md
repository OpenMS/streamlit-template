# TOPP Step Cache

A TOPP workflow runs several tools in sequence. The step cache lets a step
that was already computed under the same effective conditions reuse its
previous output instead of re-running the tool, while any step whose
conditions changed (and everything downstream of it) still recomputes.

## Key design decision: input identity is the file *name*, not its content

To avoid reading large mzML files just to decide whether a step can be
skipped, a step's cache key is derived from the **basenames** of its input
files, never their contents, size, or modification time.

```text
step cache key = SHA-256(
    input file basenames
    + cache key(s) of the directly connected preceding step(s)
    + effective parameters actually applied
    + tool version and executable identity
)
```

Consequences:

- Input file existence is not checked and contents are not read to build the key.
- Two files with the same basename in different folders are treated as the
  *same* input. If you change a `sample.mzML`'s content but keep its name,
  the cache will not detect that — rename the file, clear the relevant cache
  entries, or disable the cache for that run.
- File size and modification time are **not** part of the key.
- Input order is preserved in the key.
- In CommandExecutor, the key includes the actual parameter argument sequence,
  after filtering unknown stored parameters and converting flags, booleans and
  lists. Duplicate merged/custom arguments and their order are preserved, as
  are I/O option names and input order. Input paths still use basenames.
- The key includes tool version plus a SHA-256 of the actual invoked executable,
  separately from its optional tool instance name. Replacing that executable
  invalidates the key. External binaries invoked internally by an adapter and
  shared libraries are not automatically fingerprinted.
- Output paths and the actual number of threads assigned to the command are
  also part of the key.
- `schema: 3` / `input_identity: "filename"` distinguish this cache from any
  earlier content-hash-based scheme. Old cache entries are never deleted
  automatically.

Output corruption/tamper detection and executable-identity hashing are still
based on content checksums — only the *input* side skips reading file
content.

## Dependency chaining

```text
A = Hash(mzML/FASTA basenames + Comet config + tool identity)
B = Hash(Comet output basename + A + Percolator config + tool identity)
C = Hash(Percolator output basename + B + Filtering config + tool identity)
```

A step's key already encodes everything upstream of it, so a step never
needs to flatten every prior parameter into its own key — only the upstream
step's key.

| Change | Expected behavior |
| --- | --- |
| Nothing changed | Cache hit, reused |
| Comet settings changed | A changes, and B, C (which depend on it) change |
| Only filtering settings changed | A, B reused; C and downstream steps recompute |
| Reverted to previous settings | Old key's cache entry reused, if still present |
| Input filename changed | The key for the step(s) using that input changes |
| Same-named input's *content* changed | Not detected automatically — rename the file or clear the cache |
| Sample added | Existing independent per-sample steps can still be reused; steps that combine the input list recompute |

`StepCache.producers` maps an output file's basename to the condition hash
of the step that produced it, and is persisted to
`workflow_dir/cache/producers.json` so it survives worker restarts. Both a
cache hit and a fresh computation register this mapping, so a downstream
step always finds its upstream key regardless of whether the upstream step
ran or was served from cache.

If a sample is added and that changes per-command thread allocation, other
samples in the same batch may also miss cache, since `threads` is part of
the key.

## File layout and execution flow

```text
workspace/
└── <workflow>/
    ├── input-files/
    ├── cache/
    │   ├── producers.json
    │   └── steps/
    │       └── <tool>/
    │           └── <condition_hash>/
    │               ├── manifest.json
    │               ├── 0
    │               └── 1 ...
    └── results/
        └── current output of each step
```

The tool directory component is SHA-256 of the tool/instance name, so absolute
executable paths and instance names cannot escape the workflow cache directory.
Numbered files under a condition hash directory are cached copies of that
step's declared outputs, in the order they were declared. `manifest.json`
records the condition that was hashed, the digest, and per-output
checksums.

1. `run_topp()` builds each command as before.
2. For each process (one per sample/input), `StepCache.condition_hash()`
   computes the key from that process's actual inputs/outputs/parameters.
3. `StepCache.try_restore()` checks for an existing manifest and verifies
   every declared output's checksum before copying anything into place.
4. On a hit, the tool invocation for that process is skipped entirely and
   the cached outputs are copied to the paths the workflow expects.
5. On a miss, the tool runs. If it succeeds and every declared output
   exists afterward, `StepCache.publish()` copies the outputs into the
   cache and writes the manifest.

The cache lives under `workflow_dir/cache/`, outside `results/`, so it
survives a `results/` reset between local and queue-mode runs. The
executor logs `Cache HIT`, `Cache MISS`, and `Cache bypass` (when a tool
invocation declares no output files to key on).

The filename-based policy cannot detect a content change made to an input
file *during* a run either — inputs are assumed stable while a workflow
executes.

## Enabling / disabling

Add a top-level key to the workflow's `params.json` (do not replace the
whole file, just add or change this key):

```json
{
  "step-cache-enabled": false
}
```

Disabling the cache does not delete existing entries. If you re-enable it
after replacing a same-named input's content, an old entry may still be
reused — rename the file or clear the relevant cache entries first if that
matters.

## Upstream integration

`run_topp()` records every file in RunProgress, including cache hits (as `done`).
Misses keep their original file indices for progress and failure messages.
The public batch API retains its boolean result; an internal ordered result
list pairs each command with its cache metadata. Thread allocation is computed
for the original batch and is not increased when some files hit the cache.

Cache I/O errors are logged as warnings and disable caching for the remainder
of that executor's lifetime, so stale producer keys cannot be used downstream
in that executor. Computation still runs; successful tool results are not
changed to failures when publishing the cache fails.

See [the Korean merge record](step-cache-merge.ko.md) for code examples, tests,
the schema migration and detailed limitations.

## Scope

This covers TOPP tool invocations through the shared `CommandExecutor`.
Visualization generation, Python post-processing, and direct EasyPQP calls
are outside this cache's scope and may still run even when the TOPP steps
that feed them are cache hits.

There is currently no automatic cleanup or size limit, and the cache is
never deleted mid-run. Environment changes not reflected in tool version,
executable hash, or parameters (shared libraries, OpenMS resource files,
etc.) are not tracked — refresh the relevant cache entries manually after
such a change, or disable the cache if you need guaranteed fresh
(non-deterministic) results.
