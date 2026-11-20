This read-only review identifies a supported way to retain every signal needed by the complete D-cache access audit while limiting FST output. No model was rebuilt or executed for this review, no filtering has been implemented, and the original immutable model remains unchanged.

Recommendation: copy the preserved generated model archive and host objects, add 105 exact leaf-name `dumpvars(1, name)` selections in the copied generated `Syms.cpp`, compile only that translation unit, replace its object in the copied archive, and relink. This uses the installed Verilator tracing API and requires no SystemVerilog change or RTL elaboration. The copied executable must receive a new identity and pass a short matched validation before another data-reuse run.

The exact insertion point is the preserved `Vbsg_nonsynth_zynq_testbench__Syms.cpp`, lines 552–554: after `__Vm_modelp->trace(__Vm_dumperp, 0, 0)` and before `__Vm_dumperp->open(...)`. The original file SHA256 is `0b18a9494fc274cd95333648cba1480ee4beb9f8ac887ff755366512e9e4c687`. The proposed insertion is conceptually:

```cpp
for (const char* name : required_signal_names)
    __Vm_dumperp->dumpvars(1, name);
```

`required-signals.json` contains all 105 canonical names, copied verbatim from the frozen validated old trace's `signals` mapping. It also binds the exact installed runtime source files reviewed. The selection includes BE clock/reset, the two physical-slot logical-context mappings, retired context/PC/valid, global CSR cycle, D-cache's actual opposite clock, geometry, normal demand admission/hit/miss controls, accepted UCE-facing data/tag packet fields, actual tag write/read/mask ports, and invalidation controls. The accepted D-cache packet ports already expose the UCE's relevant refill effects; internal UCE state is unnecessary. All cached accesses remain visible, including stacks, metadata and setup. This is a signal allowlist, never a target-address or miss-only filter. SRAM data arrays are unnecessary because the program independently checks values, while the auditor validates the actual tag/access/refill state.

The installed sources establish the behavior:

| Source | Relevant behavior |
|---|---|
| `verilated_fst_c.h:248` | Public `VerilatedFstC::dumpvars(level, hier)` forwards to the trace object. |
| `verilated_trace_imp.h:431` | Positive-level calls accumulate selections and convert dots to trace-name spaces. Level zero clears the list and enables everything, ignoring the supplied hierarchy. |
| `verilated_trace_imp.h:364` | `declCode` requires an exact hierarchy boundary, counts remaining levels, and enables selected trace codes. |
| `verilated_fst_c.cpp:138` | Packed arrays concatenate their name and `[i]`; modules and packed structs create real scope separators. |
| `verilated_fst_c.cpp:179` | Unselected declarations return before creating an FST variable. |
| `verilated_trace_imp.h:825` | Value emitters still update old-value storage but skip emission for disabled codes. |

Do not normalize array names or replace them with their base names. The generated declarations confirm that `physical_thread_context_id_r` is `ARRAY_PACKED` followed by `declBus("[0]")`/`"[1]"`; the filter therefore sees the exact canonical names ending `[0]` and `[1]`. Similarly, the tag arrays use `ARRAY_PACKED` then `STRUCT_PACKED("[i]")`, producing `tag_mem_data_li[i].state` and `.tag`. Exact canonical leaf selections work for both. A parent D-cache scope with level one would omit the struct fields needed by the auditor. A coarse level-two scope would also retain many unnecessary child-port signals.

The generated `classes.mk` identifies `Syms` as a support translation unit and keeps `VM_TRACE=1`, `VM_TRACE_FST=1`. The archived original link command uses seven unchanged host/runtime objects (`ps.o`, `main.o`, `bsg_nonsynth_dpi_clock_gen.o`, `verilated.o`, `verilated_dpi.o`, `verilated_fst_c.o`, `verilated_threads.o`) plus `Vbsg_nonsynth_zynq_testbench__ALL.a`. The preserved archive is 26,864,588 bytes. Only the copied archive's `Syms.o` member should change. Keep the original compile flags and generated headers, but replace the original `-include ...__pch.h.slow` PCH alias with the actual text header `...__pch.h` after proving the original PCH creation used that header and identical flags. Use explicit compiler/archive/link commands rather than invoking the whole Verilator make target. Hash every original input and archive member, the tiny source insertion, and the new executable. Verify all members except `Syms.o` are byte-identical.

Proposed validation, requiring separate execution authorization:

1. Run the existing short full-burst off40 mode-0 ELF/NBF on the filtered copy. Require the unchanged maintained guest/host checker, same checked result and 664-cycle interval. Verify the FST is finalized and its full variable-name set is exactly the 105-name allowlist. Empty hierarchy scopes are harmless; missing or ambiguous variables are a failure.
2. Stream that entire filtered trace through the frozen auditor and compare the accepted-access/tag/fill events and timestamps against the original old trace: 4,742 cached references, 4,639 hits, 103 misses/publications, 824 fill beats and 103 completions. Preserve the matched checks, output size and host runtime. This tests the real installed runtime selection implementation and catches wrong names, array handling, alias selection or clock loss.
3. Only then repeat the same `cc97e23d...` 1 KiB ELF/NBF, retaining the native 600-second and 150 MiB bounds. Accept it only on full guest/CORE/host completion plus all independent per-context request/load-count and cache-state checks. The 32 KiB case remains gated on that result and must reuse the same ELF.

This changes trace output, not target instructions, RTL state transitions, memory timing, or the times at which trace callbacks run. It can reduce emitted/compressed data and converter work; it does not remove generated trace calculations or guarantee completion within either bound. No reduction ratio has been measured yet. The filtered binary is derived from, rather than byte-identical to, immutable model `85505d381643fca1a118c9e5d6930468e9bcce736ebfd0a926fb36419064af8b`; it must never silently replace that original identity or be pooled with it before matched validation.

The prepared `build_scoped_model.py` implements this as two explicit stages for the root agent's host namespace. The preparing agent has not executed either stage. It parses the exact archived compiler/link argv rather than invoking a make target. Before editing its copy, it directly relinks the untouched objects and requires byte-identical reproduction of the accepted `85505d38...` executable. It then permits only `Syms.cpp`, `Syms.o`, `Syms.d`, the copied archive and the copied executable to change; all other generated files, archive members and original inputs are hash checked. Compiled PCH `.gch` files are excluded from the copy. The second command runs only the existing mode-0 program (native 240 seconds, host guard 300 seconds, hard 150 MiB trace limit), checks its 664-cycle interval/checksum and exact 105-name header, and requires byte-identical complete accepted-event JSONL streams from original and filtered traces using the frozen auditor. Any failure stops the gate. Neither command runs or admits the new 1 KiB program.

Example commands for the authorized root agent (use new output directories):

```sh
python3 research/resume-data-reuse-20261120/trace-filter-review/build_scoped_model.py build --output /dev/shm/zp-linux-resume-capacity-20261120/burst-off40-scoped-v2
python3 research/resume-data-reuse-20261120/trace-filter-review/build_scoped_model.py validate-mode0 --build /dev/shm/zp-linux-resume-capacity-20261120/burst-off40-scoped-v2/evidence/build.json --output research/resume-data-reuse-20261120/scoped-mode0-validation-v2
```

Validation output must be retained durably before any RAM cleanup. The original old mode-0 program files are copied and hash checked verbatim, so the existing aligned NBF mode patch is preserved without recompilation or repatching. Modes 1–3 are not repeated.

The root agent's first build attempt reproduced the accepted binary exactly from the untouched copied archive, then failed at the explicit Syms compile: `fatal error: Vbsg_nonsynth_zynq_testbench__pch.h.slow: No such file or directory`. My initial driver incorrectly assumed that the `.slow` include alias had a text header. The original directory contains `...__pch.h` plus `.fast.gch` and `.slow.gch`, and the archived creation command is `g++ <flags> -x c++-header ...__pch.h -o ...__pch.h.slow.gch`. The corrected driver verifies the PCH command's complete flag prefix equals the Syms command's prefix before changing only the `-include` operand to `...__pch.h`. It records both original commands and the actual text-header hash. The first attempt is preserved; no target execution occurred. `driver-preflight-v2.json` records successful read-only validation of this mapping. The corrected driver has not been built or executed by the preparing agent.
