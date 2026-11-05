This summary records the accepted end-to-end version-2 synchronous-fault gate without committing generated simulator or FPGA transcripts. It retains the exact model, image, route, runner, and transcript identities needed to audit or reproduce the result.

# seL4 protected-RPC V2 fault evidence

The accepted fault-only seL4 simulation used a freshly rebuilt
two-thread/four-context model from BlackParrot
`7ad23b7c697e75b3519f19ffb41884210dc3f823`. The strict checker accepted all
three region denials, binding, one committed server-fault return, terminal
retry, privileged fault-record consumption, fresh rebind, a normal hardware
call, and the exact `Test SEL4IPCRPC0002 passed` verdict.

The same NBF passed on the physical PYNQ-Z2 with the timing-clean routed image.
The serialized foreground runner reached the exact test verdict, `CORE PASS`,
`BSG PASS`, and exit zero; the strict physical checker accepted the run.

## Full-system simulation identities

- Model SHA-256:
  `e5c1e823423b202368b33c66565210371b42d566b5c6d1b2ff922fe862701651`
- NBF SHA-256:
  `81ebb02c94127f2008164d1482c8a7c0a69bf0b2461f385efaee659b5b624fd2`
- Raw transcript SHA-256:
  `698ddbc06ed5def8be39275eef94aff2073929cbed189e62556a391cba94febf`
- Compressed transcript SHA-256:
  `2c834e0f9829494ec54de5308b7d07cbe826940b5ccc85480c84afb12e1605d6`

## Routed and physical identities

- Top-level route commit: `efb2e5b04c1203b0d8175e4e018c4e8fa87b8f7d`
- BlackParrot commit: `7ad23b7c697e75b3519f19ffb41884210dc3f823`
- Configuration: `e_bp_unicore_zynqparrot_sel4_cfg`
- Timing: WNS `+0.221 ns`; WHS `+0.012 ns`; no negative setup or hold slack
- Utilization: 49,215 LUTs; 24,581 registers; 88 BRAM tiles; 11 DSPs
- Package SHA-256:
  `3ea7effc89402c40ba12951f47ed03b8f95729ef8269e8317741cced17ec5b5d`
- Bitstream SHA-256:
  `c9cd7006d8501d25cf7981f16a2757c0b13461212b6cca4973163994f1da81f2`
- NBF SHA-256:
  `81ebb02c94127f2008164d1482c8a7c0a69bf0b2461f385efaee659b5b624fd2`
- Runner SHA-256:
  `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`
- Raw physical transcript SHA-256:
  `e78b6643f4ca2c28344237b782c6f1c1d753d9a1fca57da2a070566c40d49498`
- Compressed physical transcript SHA-256:
  `7780975d18136c4220d829adefa2f77c4f8813fbf73d9807570e2e55d46d57f3`
- Retired-instruction delta: 8,767,887
- MTIME delta: 8,268,978 eighth-cycle ticks
- Host wall time: 1,653,818,797 ns

An earlier failure used a different, unqualified model (`5c059f5e...`) and is
not evidence against the accepted arbitration fix. The physical image injects
illegal instruction only; the instruction/load/store page-fault matrix is
separate directed full-core simulation evidence.
