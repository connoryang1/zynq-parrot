This directory preserves the simulator evidence for locking legacy context-control and diagnostic interfaces after protected-RPC descriptor installation. It also records the descriptor-install metadata repair required to keep a bootstrapped server in its original U/Sv39 domain.

# Protected-RPC legacy-interface lock

The initial lock correctly denied U/S writes to context switch, NPC seed, remote-register seed, cache-service, and miss-trace controls, while retaining M-mode setup access. The first test exposed a separate ordering bug: installing the descriptor after the server bootstrap replaced context 1's saved privilege, translation-enable, and ASID with the M/Bare installer state. The accepted RTL updates only the descriptor NPC/APC during descriptor installation and preserves the target's previously initialized domain metadata.

The final audit also gates reads of CSR `0x803`, `0x804`, `0x805`, and `0x807`. The test seeds nonzero cache-service data and an armed miss trace in M mode before descriptor installation, then proves that the locked U-mode caller reads zero from all four interfaces. Completion uses an ordinary U-mode `ecall`, because a successful lock intentionally makes the old U-mode context-switch finish path unavailable.

The exact 2-thread/10-context traced run reports guest/host PASS, preserves distinct caller/server private pages, rejects invalid protected-call and return operands, and measures direct service at 193/31 cycles and protected RPC at 114/43 cycles. The legacy context-switch smoke also passes, and the raw transport regression remains exactly 224/31 direct and 179/109 RPC cycles. The simulator's known DPI finalizer assertion occurs after `CORE PASS` and `BSG PASS`; the harness classifies each run as valid.

`accepted-contexts4*` and `accepted-contexts10*` preserve the pre-read-lock validation. `accepted-contexts10-read-lock*`, `source.c`, and `disassembly.txt` are the final adversarial checkpoint. Routed timing and physical FPGA execution of this security increment remain pending.
