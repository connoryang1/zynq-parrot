This read-only diagnostic explains why the completed advisory fixture does not qualify as retained restoration evidence. It reads additional PF installer signals from the same closed raw07 waveform, with no new target execution, RTL change or performance comparison. The strict hit/refill gate remains failed.

The reset-qualified validator in `trace-audit03-child` consumes actual exit134 under the maintained post-PASS GPIO exception policy. It decodes the complete closed FST without a post-reset protocol violation, then rejects missing I publication/hit/refill evidence. Both lanes have no accepted retained insertion or publication after reset. This is separate from the earlier analyzer's pre-reset rejection, whose source and partial events are preserved under `research/retained-control-abi-20261121/advisory-trace-validator/rejected-pre-reset01`.

The additional selected direct-FST events show completed advisory replies entering the normal resident scan while enabled:

| Lane/target | `check_tag` with tag match1, probe way1, full1 | Next `drop` state9 |
|---|---:|---:|
| I/0x80001000 |6,028,125,000ps |6,028,175,000ps |
| D/0x80012000 |6,029,150,000ps |6,029,200,000ps |

The exact compiled UCE's `e_pf_check_tag` branch drops a completed advisory line when `prefetch_install_tag_match` is true. Neither line reaches retained publication. Thus nominally touching ten same-set lines did not establish the fixture's intended coldness; the trace records the resident-drop guard taking effect. No missing request, retained SRAM corruption or hardware root cause is established. The fixture requires an independently verified coldness control before a new run can qualify the retained payload path.

`diagnostic.json` binds the same FST SHA, exact critical compiled RTL, source-list identity, selected-event dump and selection. Its algorithm samples stable pre-edge UCE values after observing reset. The parent's run/admission artifacts bind the unchanged consumed model, fixture ELF/NBF, completed transcript and expected assertion scope. This diagnostic does not treat a guest PASS or sampled controller activity as retained-hit proof.
