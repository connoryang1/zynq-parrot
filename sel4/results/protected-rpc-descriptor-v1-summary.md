This summary records the accepted version-1 descriptor and protected-call evidence without committing generated binaries or raw simulator transcripts. The tests are reproducible from the committed sources and their original artifact identities remain listed for provenance.

# Version-1 protected RPC evidence

Four serialized, traced full-core regressions passed on the same clean
Verilator model:

- `control` staged all nine descriptor fields; rejected incomplete,
  equal-SATP, unsupported, and incompletely prepared descriptors; proved that
  restaging invalidates preparation; and checked token-aware query and revoke.
- `hardware` used distinct U-mode Sv39 address spaces and resident contexts,
  rejected an invalid token before execution, installed the fixed
  entry/SP/GP/TP/badge, transferred four request/reply words plus metadata, and
  consumed the protected continuation. Deliberately dirtied server registers
  were zero at first entry. Matched local first/repeated timing was 250/31
  cycles versus 396/58 for protected RPC, a stable 27-cycle warm premium.
- `library` exercised the reusable wrapper and separately linked service page,
  preserving checked shared offsets and distinct private mappings.
- `smoke` confirmed that ordinary context switching remained operational with
  the descriptor RTL present.

Every transcript reached its test-specific guest marker, `CORE PASS`, and host
`BSG PASS`. The later DPI GPIO finalizer assertion is a known post-pass
simulator teardown defect and was accepted by `testing/check_run.py`.

## Reproducibility identities

- Verilator model SHA-256:
  `5925788e632135b9cc1b705d1c8e5fb3d07be2b77a15c7176bcd5ebecb3456bc`
- Fresh pinned OpenSBI/seL4 package NBF SHA-256:
  `cbc2b526ae59141168b3df45c0b069e4b08a007248d85bb3f6bd7e679b672f79`

| Artifact | SHA-256 |
| --- | --- |
| control ELF | `2c436d97e14d3fbab23617417e9e343117517c2276aec1b3222f35bf937e2ba6` |
| control NBF | `150b39b44e3d87ee1fd5eb651cc995ac05d7900a1680a210292b00579971d54c` |
| control transcript | `7c08d0c38955e5f4a7826d892afc01f96318873cfa15b56b6957eb81fa5ca423` |
| hardware ELF | `f4e50c1949cac41303eb340c202baaa3829f54bb6d147f8e025159de606e000a` |
| hardware NBF | `e5f258383fb19b522c907366f03775f90c037747d0e3f3e2f627cf932e76ceff` |
| hardware transcript | `a7721c6f66dc152fc555c69fea4d99c942b74c5e23942cda6c4c7fe239af537e` |
| library ELF | `8aba5519ddf03314102c9c717ec73a21239dc63386ca310740a6d1c2eb647c95` |
| library NBF | `c8938819ab142aba885a52075f8cba642c5aa9d7456a0541f187640ba4be7ee1` |
| library transcript | `21e0e5d4c85b1c9387d73f3a26e930c2ccb594b307412cd4d2f8de11568f1a45` |
| context-switch smoke ELF | `43744d196cdc7f7f0b0f94381c1711b35c6af29058b62c24f506f042f9ae566a` |
| context-switch smoke NBF | `6ac7b750883153b8b08593c231b6ac76ed4acd3e31795372930742e8386a2627` |
| context-switch smoke transcript | `227bde66ac6532dc5a267949738083f303af66ae67d844803e5ad802419d3e3d` |

This checkpoint establishes the hardware mechanism. It does not independently
claim the later seL4 binding, routed timing, physical execution, or version-2
fault policy.
