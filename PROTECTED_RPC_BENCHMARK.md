This document defines the focused protected-call performance benchmark for the resident `pcall`/`preturn` mechanism. It separates boundary latency from useful service work and keeps the benchmark independent of the later Linux or cryptographic application experiments.

# Protected RPC call benchmark

## Question

Can the hardware-protected resident call approach an ordinary function call for a small trusted service while preserving a caller/server address-space boundary?

The benchmark is a protected-procedure-call microbenchmark, analogous in purpose to established microkernel IPC latency tests. It is not a general RPC throughput benchmark, a Linux syscall benchmark, or a cryptographic primitive benchmark.

## Matched modes

The first implementation is intentionally staged around the existing validated
RPC images.  The new `mt_protected_rpc_call_benchmark` target executes a matched
64-call direct/protected loop in one image; the existing software-monitor and
raw-transport programs remain separate controls until their call loops are
ported to the same harness.  This keeps the first result small and reviewable
without pretending that separate front-end histories are a fully matched
four-mode experiment.

The intended comparison matrix is:

| Mode | Boundary | Purpose |
| --- | --- | --- |
| Direct | ordinary in-domain function call | lower bound for useful work plus call/return |
| Software protected | software monitor/context handoff | software isolation baseline | 
| Raw transport | existing CSR argument transport and context switch | unsafe hardware transport bound | 
| Protected hardware | installed capability with `pcall`/`preturn` | proposed mechanism | 

The caller and server use distinct private mappings and one explicitly shared page. Each mode uses the same arguments, service body, result check, context setup, and first/warm call structure. Result validation is outside the timed interval except for a server-side result publication required by the service contract.

## Service bodies

The initial image uses three integer-only service sizes:

1. empty register transform: four arguments combined into one result;
2. shared-buffer transform: four arguments plus one fixed shared-page load/store;
3. small memory service: a fixed bounded checksum over a prefaulted shared buffer.

The service must not block, fault, allocate, use floating point, or access the caller-private page. The server's private key/state analogue is represented by a private mapping and checked after the timed loop.

## Measurements

For each service size, report:

- first-call cycles;
- warm-call median and spread over repeated calls;
- total cycles and calls per cycle for a fixed batch;
- direct-call premium of each protected mode;
- exact argument/result and private/shared-memory checks.

The primary boundary metric is the warm protected-call premium over the matched direct call. The useful-work sweep shows when that fixed premium becomes negligible. The existing protected test's 43-cycle warm RPC versus 31-cycle warm direct result is retained as the initial reference, not silently replaced.

## Initial simulator result

The first implementation passes the 2-resident/4-logical-context Verilator gate
with 64 identical calls in each loop:

| Path | First call | Warm call | 64-call total | Result sum |
| --- | ---: | ---: | ---: | ---: |
| Direct | 0xc2 (194) | 0x1f (31) | 0x7c0 (1,984) | 0x9e200 |
| Protected hardware | 0x72 (114) | 0x2b (43) | 0xac0 (2,752) | 0x9e200 |

The protected boundary is therefore 12 cycles, or 38.7%, above the warm
direct-call baseline for this service body. Both loops produce the same summed
result and preserve the existing private-page checks. This is a simulator
result, not an FPGA result; the final routed/physical check remains an
end-of-line gate.

The software-monitor and raw-transport rows are not claimed yet. They require
the same repeated-loop treatment before they can be compared fairly.

## Scope and gates

The benchmark is simulator-first and uses the exact two-resident/four- and ten-logical-context topologies already required by the RPC tests. It must pass the existing protected-RPC correctness and privilege-lock tests before its numbers are interpreted. A final routed/physical run is one end-of-line checkpoint only; no FPGA build belongs in the foreground iteration loop.

This benchmark does not claim a general microkernel IPC result. A later MAC, packet-authentication, or Linux service experiment may reuse its service-body pattern, but must be a separate workload and must not change this boundary benchmark's interpretation.
