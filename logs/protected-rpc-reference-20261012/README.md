This directory records the first executable protected-RPC reference and its matched ordinary-call control. It fixes the software semantics and quantifies where a hardware `pcall`/`preturn` path can remove work before any new RPC RTL is designed.

# Protected RPC software reference

The test runs a caller and server as separate U-mode Sv39 protection domains.
Only a shared data page is common: the same private virtual address maps to
different physical pages, each domain has a separate stack and executable
page, and neither U-mode page table maps the M-mode reference monitor. The
monitor validates one caller/capability pair, enters a fixed server PC, passes
four register arguments, holds the return continuation in M-only memory,
accepts `preturn` only from the active server, returns one register result, and
scrubs all other caller-saved state at both boundaries.

The matched ordinary function executes the same private store, shared load,
two additions, and shared store. The measured interval includes argument setup
and cycle-counter reads in both cases. The test passed with test-specific and
common guest/host markers under the clean trace-enabled two-thread/four-context
model.

| Path | Cycles | Extra vs direct | Ratio vs direct |
| --- | ---: | ---: | ---: |
| Ordinary same-domain call | 76 | 0 | 1.00x |
| Protected first call, flush on both switches | 824 | 748 | 10.84x |
| Protected repeat, flush on both switches | 450 | 374 | 5.92x |
| Protected first call, distinct ASIDs retained | 773 | 697 | 10.17x |
| Protected repeat, distinct ASIDs retained | 287 | 211 | 3.78x |

The retained-ASID mode is safe for this reference because the two immutable
page tables use the implementation's two distinct ASIDs, zero and one. Mapping
changes would still require the normal targeted invalidation before reuse.

The repeat-call waveform divides the 280 cycles from caller ECALL dispatch to
the first resumed caller instruction as follows. The cycle-counter interval is
287 because it starts before argument/opcode setup and ends at the following
counter read.

| Dispatch boundary | Cycles |
| --- | ---: |
| caller ECALL to first M-mode handler instruction | 57 |
| entry handler instruction stream to first server instruction | 109 |
| server useful instruction stream through `preturn` ECALL | 25 |
| server ECALL to first M-mode handler instruction | 6 |
| return handler instruction stream to resumed caller | 83 |

Thus 192 cycles are directly spent executing the two monitor instruction
streams, and another 63 cycles are trap-to-handler transition time. The first
hardware target is an atomic descriptor transition that performs capability
check, fixed-entry selection, address-space/context selection, protected-return
installation, and the inverse return transition without walking those handler
instructions. The 25-cycle server body remains useful work.

`flush-every-switch.log` and `asid-retained.log` are accepted simulator
transcripts. `asid-dispatch.tsv` and `extract_rpc.c` retain the waveform-derived
boundary calculation; the local FST SHA-256 is
`a6619059f7ea0c29be3fc73b9a71e6434c22970fc47ee779f521a9c400fb30ee`.
The final NBF and ELF SHA-256 values are
`9bc17c3df3cbc31a4a90a3f610a60b907973724cd8481c43e192059e9b385ec5`
and `919724927f922c9b93cfa75441866f1b8c455e5e16252621bfc8015511d90752`.
