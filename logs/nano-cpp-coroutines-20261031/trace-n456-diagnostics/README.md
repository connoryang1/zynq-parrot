# N=4/5/6 worker discontinuity trace

This simulator-only diagnostic explains why worker mode takes 5,904 cycles at
N=4, falls to 2,710 at N=5, and returns to 5,962 at N=6. No FPGA was used.

All three traces use top `b9aa118177c8993c316ae9f463a669fb67e315fe`,
BlackParrot `6c79a42107a3857e63b6f47bc2468fe4599c5bff`, and ELF SHA-256
`24c6463c32da402fa28b7058acaea75e91d65492e56a31a598ef73852ffe8ce7`.
The configuration is two physical threads, ten logical contexts, ten detached
prefetch entries, worker mode 2, 200-cycle pipelined AXI reads, and queue depth
ten.

## Result

The earlier dropped-data-hint hypothesis is rejected. N=4 accepts 44 detached
hints, consumes 44 matching loads, and makes zero ordinary D-cache UCE reads.
N=6 similarly accepts and consumes all 66 hints with zero ordinary data reads.
Their peak detached-hint occupancies are four and six. Time-weighted occupancy
is 1.543/3.527 for N=4 and 2.292/5.159 for N=6 over the complete/active
intervals.

Both slow rows instead launch two consecutive accepted I-cache requests for raw
word address `0x800003c0`, corresponding to byte line `0x80000f00`, while the
terminal worker is retiring PCs `0x8000061a` and `0x8000061e`. That fetched line
contains the C++ coroutine scheduler and is not on worker mode's architectural
path. The request stream blocks the redirected worker fetch until its final
response; retirement resumes seven or eight cycles later.

| Event | N=4 cycle | N=6 cycle |
| --- | ---: | ---: |
| Terminal worker result store, PC `0x8000061a` | 2,501,859 | 2,548,619 |
| First/second accepted I-cache request | 2,501,859 / 2,501,860 | 2,548,619 / 2,548,620 |
| Context-cache target launch | 2,501,867 | 2,548,627 |
| Critical I-cache response | 2,502,270 | 2,549,030 |
| Final I-cache response | 2,505,098 | 2,551,858 |
| First target-context retirement | 2,505,106 | 2,551,865 |

The first request-to-final-response interval is 3,239 cycles in both runs.
Context-cache launch itself completes in three cycles, so register save/restore
does not explain the gap. N=4 has 3,271 cycles between its final useful data load
and timer end. In N=6 the same front-end stall occurs before contexts four and
five finish, leaving only 50 cycles after the final useful load. N=5's complete
2,710-cycle interval is shorter than this single refill episode, so it avoids
the event in this executable/cache state.

The practical conclusion is that N=5 is the best measured point but not a
capacity-derived optimum. Its 1.982x worker/coroutine result is sensitive to
instruction-cache state, off-path fetch, and layout. It should
not be generalized as “five shards is optimal” without controlling or removing
this front-end artifact.

## Evidence qualification

The N=4 and N=6 benchmark transcripts pass result, checksum, guest, core, and
host checks. Their transaction analyses are valid. The N=5 benchmark transcript
passes at exactly 2,710 cycles, but its general transaction analyzer rejects the
waveform before the measured window with a normal-response boundary mismatch;
no N=5 occupancy claim is made from it.

The large FSTs could not be copied into the repository because the workspace
filesystem had only about 189 MiB free. They remain in tmpfs for this session at
`/dev/shm/nano-trace-n456-20261031.B1opJf/artifacts/` with hashes:

- N=4: `3121a4b4d4ba3aa3397a8cf713d4c2cf48eeaa1c807f110b2ca4c9fbfe95767d`
- N=5: `ca5695215b6c58260ba4515f141202d3e7cd38e8f5b7aa71828c02cfbf9c051e`
- N=6: `c1a5260b8e1d8c5cbf32be7ec7a89de299b5502f9ee5314821a94c68e95208aa`

The I-cache scan used the real `icache_req_v_lo && icache_req_yumi_li`
handshake plus `icache_req_critical_li` and `icache_req_last_li`. The optional
cache-miss recorder was disabled (`cache_miss_trace_p=0`) and its empty output
was not treated as evidence. Setup also required propagating `TOP` into the
isolated harness and installing the generated hardware makefile before the
trace build; both issues were corrected before these runs.
