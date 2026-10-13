This directory records the physical rejection of the first routed context-switch interlock. It preserves the exact guest transcripts and distinguishes guest `CORE FAIL` from the host control program’s normal final `BSG PASS`.

# First routed interlock: rejected

The tested image used top commit `65f30750`, BlackParrot commit `6c79a421`, and bitstream SHA-256 `8f703740...c13`. The exact ten-stream NBF that failed twice on the prior image (`cfa9eded...c7df`) again produced `CORE FAIL` on two fresh-overlay runs. The exact two-stream control (`92b0bdbe...a5b0c`) produced its test-specific marker, `CORE PASS`, and 19,262 cycles, exactly matching the prior physical result.

The image is therefore healthy, but the interlock does not repair the corruption. Waveform review explained why: `ctxtsw_target_settle_r` pulsed immediately after commit while the issue queue was empty, then cleared before the redirected target instruction reached the queue. This rejected implementation did not create the occupied target-dispatch cycle supplied by the successful software bubble. `results.json` pins every revision, artifact hash, run result, and retained transcript hash.
