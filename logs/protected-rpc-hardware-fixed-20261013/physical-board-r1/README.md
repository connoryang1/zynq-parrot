# Invalid cross-configuration protected-RPC board attempt

This directory records an invalid physical comparison. The route used
`e_bp_unicore_zynqparrot_cfg`, while the accepted context-switch route and all
three NBFs below target `e_bp_unicore_zynqparrot_prefetch5_cfg`.

- Top-level revision: `e7acfbe5eeff7f9379fc718e30ad661ab093c68f`
- BlackParrot revision: `2ff7ea31aa9971e4b7de601dfcc8765df58c280c`
- Package SHA-256: `783da4fb426c746e39ee5d68109457eef96fda45143ef4446da7cc04c2f1ec5a`
- Bitstream SHA-256: `7e80ce29ee6e5db9308cfb32fd6495ab8f4db2af780535b4b44df96e484bfe8a`
- Protected test NBF SHA-256: `8f32109fef86a36d5371b8b0401bf4b49029fca57ee5eb8cf10c46f9992e42b0`
- Raw RPC control NBF SHA-256: `6e29bf18355cd492554b4f1f74a85fb1579991af5695007be9f8382b21b3a0c4`
- Previously accepted exact k2 NBF SHA-256: `92b0bdbe635486053a23ca9fc86074678a8f28b11e07626d43a23a11af6a5b0c`

The package verified, the overlay loaded with the expected bitstream hash, and
the FPGA manager reported `operating`. The protected workload and matched raw
RPC control each loaded completely and retired about 18.7k instructions, but
both timed out after 180 seconds without guest output. The exact k2 image that
passed the preceding routed baseline at 20,547 cycles instead failed
immediately with `dependent stream result mismatch; stream=1`. These outcomes
are the expected consequence of running prefetch5-configured programs on the
stock configuration and say nothing about protected-RPC correctness.

The resource mismatch was also configuration-driven: this route used 22,186
registers and 82 BRAM tiles versus 27,995 registers and 85.5 BRAM tiles in the
accepted prefetch5 route. The cleaned replacement candidate keeps RPC operands
in a dedicated scheduler register and restores the original nonresident SRAM
interface. Simulator results remain 220/31 direct and 90/66 protected, with
the raw regression still 224/31 and 179/109. A correctly configured route and
physical acceptance are pending.

The board runner reported process exit zero for the k2 control because this
historical image calls the host finish path after printing its own failure.
The guest's explicit `[BSG-FAIL]` and `CORE FAIL` markers are authoritative.
