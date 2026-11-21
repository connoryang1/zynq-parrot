This directory preserves the exact post-program helper fix and its operational protocol evidence. It addresses a plausible stale filesystem-metadata failure without changing the PID guard, timed guest work or frozen eight host sources. All implementation tests are local fixtures; board inspection, bounded stale-owner removal, atomic installation and physical retry belong to the coordinator.

# Post-program cleanup sync and executed-source evidence

The helper adds seven lines only inside its existing EXIT cleanup: sync after writing program status and removing its program-lock owner/directory, fail closed with exit 74 if sync fails after a successful program, hash the actual `$0` helper path, print `BOARD_RUNNER_SOURCE_SHA256`, and exit with the preserved nonzero program result or cleanup result. Precleanup guard/validation bytes and everything from `trap cleanup EXIT` through launch/program exit remain unchanged. The common global reservation lock is never removed or recreated.

| Artifact | SHA-256 |
| --- | --- |
| Original helper | `8b0f12b655d3bfc071e96d5b05018971500dcc125ca88936ce28eae6f971c283` |
| Final cleanup-sync/self-marker helper | `de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90` |
| Reviewed protocol manifest | `8325114ac9affefdfa6fe24811edcfa8b1feb7d7888d554ba5b29135dded833f` |

`protocol.json` binds original/final source snapshots, the complete source diff, operational addendum, read-only inspection and known-owned cleanup. The original unmarked sync proposal is preserved under `*.unmarked-draft.*`; it was superseded before deployment and is not eligible for new-phase admission. The final protocol pin and final source are the only accepted new versions.

## Diagnosis and scope

Inspection found no active program and a stale owner/directory predating the current board boot, associated with the preceding completed program. The coordinator removed only the known-owned preboot program lock under a separate global reservation and synced, with the global lock untouched. These facts make unpersisted cleanup a plausible cause; they do not prove filesystem resurrection or explain unrelated earlier failures. Raw failed session23/session23-retry1 evidence remains preserved. Their completed partial parse is diagnostic only; the whole failed two-program slot must be retried without selecting according to an effect.

On an admitted successful run, the new work follows completion of `script`, so it occurs after guest PIPE_HINT/CORE/BSG and outside every measured cell. Failed programs may run cleanup after termination too, without becoming admissible. `RUNNER_EXIT` still records the original program result, while outer sync failure remains nonzero. Existing PID checks, CLI arguments, target-runtime limit, guest code, NBFs, bitstream, resource/WHOLE endpoints and all primary estimators remain unchanged.

## Explicit helper-version transition

The low-level helper is not in the original frozen eight, so its change is explicitly recorded rather than hidden behind that omission. The first three admitted visits use legacy source without a per-run source marker. Remaining visits require the final helper. The coordinator must read and bind the actual remote original hash, atomically replace the fixed helper with no active program under the global reservation, then read and bind its actual new hash.

The acquisition registry is:

```json
{
  "board_helper_protocol": {
    "review_sha256": "8325114ac9affefdfa6fe24811edcfa8b1feb7d7888d554ba5b29135dded833f",
    "installation": {"path": "/absolute/path/to/installation.json", "sha256": "ACTUAL_INSTALLATION_SHA256"},
    "visit_versions": {
      "A1-first": "8b0f12b655d3bfc071e96d5b05018971500dcc125ca88936ce28eae6f971c283",
      "A1-second": "8b0f12b655d3bfc071e96d5b05018971500dcc125ca88936ce28eae6f971c283",
      "B1-first": "8b0f12b655d3bfc071e96d5b05018971500dcc125ca88936ce28eae6f971c283",
      "B1-second": "de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90",
      "B2-first": "de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90",
      "B2-second": "de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90",
      "A2-first": "de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90",
      "A2-second": "de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90"
    }
  }
}
```

Installation JSON records `verified_utc` with timezone, `before_sha256`, `after_sha256`, `active_programs: []`, `reservation` identifying the common lock, `atomic_replace: true`, and `remote_helper_path` equal to `/home/xilinx/zynq-parrot/cosim/black-parrot-example/zynq/run-blackparrot-interactive`. The audit requires installation after all three old complete visits and before every new complete visit, checks all reviewed source/evidence bytes and verifies the exact cleanup-only diff.

Every new-phase transcript must contain exactly the final self-source SHA after all required program terminals. Missing, wrong, duplicate or early markers fail admission. Legacy phase markers are required to be absent and explicitly labeled legacy evidence. This checks the installed fixed-path helper at each completed execution, instead of assuming a local edit deployed it. Analysis propagates the reviewed operational change; frozen-eight equality, admission SHA501d, primary estimators and all complete-session/counter/bounds/whole-cell gates remain intact.

## Local verification

Four tests extract the actual cleanup function and invoke it in an isolated Bash fixture with temporary lock/status variables. They preserve HOME, never run the helper's top level and never execute real board, control-program, SSH or sync commands. Tests prove status-before-unlink, unlink-before-rmdir, sync-after-removal, marker-after-sync, the exact marker hash using the original script path as Bash `$0`, successful and failed program exit preservation, and sync-failure rejection. Bash syntax passes.

The expanded fixture suite passed 36 tests, including missing/incorrect helper review, altered source mapping, installation identity/path/atomicity/time boundary, actual per-run source markers, strict audit revalidation and unchanged primary-analysis behavior. Python compilation and diff whitespace checks passed. `verification.json` binds the final implementation hashes and records that no board actions or primary-effect reads were performed by this task.
