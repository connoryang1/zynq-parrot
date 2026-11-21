This addendum records an explicit operational source change during the fixed matrix. It changes only post-program durability cleanup in a board helper outside the frozen eight-source list, and does not treat that omission as permission for an unrecorded change. The fixed admission SHA `501d6b12eb0fa10b9f1d298a2be6cb365695c2be7aac96b0984ea4ffe5f4a360`, guest ELF, images, bitstream, parameters, primary estimator and stopping rules remain unchanged.

# Post-program cleanup durability

## Recorded failure and bounded diagnosis

Session23 and session23-retry1 are preserved as failed complete-session attempts for the B1-second slot. Retry1's parse program completed, but the following chase program was rejected before launch with `ACTIVE_RUNNER` and exit 75. The maintained wrapper recovered before releasing its global reservation. The complete parse remains a separately identified diagnostic; it is excluded from the primary matrix because its two-program session was not complete. Retrying the entire fixed slot is a completeness rule, not selection according to a measured effect.

The reserved read-only inspection found no active control programs and a board program-lock owner PID 1359 associated with the preceding completed parse log. The owner and directory modification time `1795224328` preceded the current boot estimate `1795224670`. The old helper removed the owner and directory at program exit without a durability sync before the wrapper's subsequent power cycle. Persistence of stale filesystem metadata is a plausible explanation, not a proved cause of the failure.

The coordinator then removed only that task's known-owned completed preboot program-lock owner/directory under a separate exclusive reservation, after matching owner/hash and confirming no active program. It called `os.sync()`. The common global lock inode was untouched, and no program, reset, overlay, NBF or other artifact was changed. The inspection and bounded cleanup manifests are retained and hash-bound in the reviewed operational evidence.

## Exact helper change

The source is `codex-skills/bp-fpga-synthesis/scripts/board_run_pynq_interactive.sh`, installed on the board as the existing fixed-path interactive helper. Its original SHA is `8b0f12b655d3bfc071e96d5b05018971500dcc125ca88936ce28eae6f971c283`; the cleanup-sync version is `de54badda52bcf716daaed5155d9be8674b3f0c137e0e411be075c7685c1db90`. Exactly seven lines are added inside the existing EXIT cleanup after status writing and removal of the program-lock owner/directory. The function calls `sync`, emits `RUNNER_CLEANUP_SYNC_FAILED` on failure, substitutes exit 74 only for a previously successful program, hashes its actual `$0` script and prints `BOARD_RUNNER_SOURCE_SHA256`, then explicitly exits with the preserved program failure or final cleanup result.

Prelaunch PID/lock guards, argument checks, hashes, runtime limits, command construction, `script` invocation, status-field spelling and all protocol fields remain byte-unchanged. `RUNNER_EXIT` retains the program's original result. A failed sync produces a nonzero outer exit and cannot satisfy maintained complete-run admission, including when the program itself returned zero. Existing nonzero program results remain nonzero and retain their exact codes.

On an admitted successful run, cleanup executes only after `script` has returned from the completed program; guest PIPE_HINT, CORE and BSG completion precede that return. The added sync is therefore outside every timed guest cell and after the program endpoint. Failed programs may also execute this cleanup after termination, without acquiring performance eligibility. The change adds no guest instruction, measurement, fence, delay knob, memory-latency setting or alternate workload, and does not change the frozen eight source bytes.

## Explicit version transition and retry

The first three admitted reservations (A1-first, A1-second and B1-first) used the legacy helper without a per-run helper-source marker. B1-second is retried in full after the recorded installation of the cleanup-sync helper; that version then remains fixed for the remaining B2/A2 reservations. Installation must read the actual remote old helper hash, replace the helper atomically under the global reservation with no active program, and verify the actual remote new hash. Every new-phase execution must print exactly the new helper hash after PIPE_HINT/CORE/BSG termination; an old or differently modified helper cannot silently satisfy new-phase admission. A local source hash alone is insufficient.

The acquisition must bind the reviewed old/new source snapshots, exact diff/source-only post-program proof, this addendum, inspection and known-owned cleanup evidence, installation evidence, and the per-visit helper-version map. The final strict audit validates the transition boundary and each new execution's marker rather than silently treating all helper sources as identical.

Installation and physical known-flow retry remain the coordinator's responsibility under the agreed reservation protocol. No physical test or board change was performed by the offline implementation agent. A durability hypothesis does not establish the cause of earlier failures or permit any change to the primary estimator, complete-session rule, carryover limits or controller-only scope.
