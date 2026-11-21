This read-only analysis explains why raw07's original warm-up did not evict its target lines. It replays the existing closed selected-event transcript and checks actual demand refill packets, index0 tag installations and instruction retirement. No fixture, RTL, model, target execution or performance measurement changes are involved.

The address and execution assumptions are correct for the trace: both targets and every4096-byte-spaced evictor use index0 of the unchanged64-set,8-way,64-byte-line L1 geometry. Target0 fills way1 in both caches; way0 already contains CRT state (I address0x80000000, D address0x8001d000). The actual refill-way sequence is:

| Target/evictor line |0 |1 |2 |3 |4 |5 |6 |7 |8 |9 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| I way |1 |2 |3 |4 |5 |6 |7 |0 |4 |2 |
| D way |1 |2 |3 |4 |5 |6 |7 |0 |4 |2 |

All first-beat refills have accepted normal cache writes and the expected one-hot bank strobe, without I abort at those beats. Ordinary tag-install events independently agree with those addresses and ways. All nine evictor functions retire16 instructions each; code0 retires32 total (warm and later demand). The target-word load instruction retires8 times, and the evictor-line load instruction9 times. The linked disassembly computes target offsets at8-byte stride and evictor offsets at4096-byte stride, so omitted work or a compiler stride mistake does not explain the residency.

The observed choices match the actual compiled Basejump binary-tree pseudo-LRU policy. Once the invalid ways have filled in order, touching ways0..7 leaves its direction bits zero; subsequent victims are0,4,2. Those three replacements leave way1 intact. This is a source-derived explanation of observed victims, not a claim that hidden LRU bits were directly sampled. It establishes why counting distinct accessed lines as though replacement were true LRU was insufficient. The later PF installer resident matches in way1 are consistent with these refills.

The smallest fixture correction is to leave target0 untouched before advisory and warm only code/data1..9, checking the data sum54. The targets are file-backed payloads written by NBF outside the CPU L1 path; the data target is not BSS. Startup/BSS bounds and lack of hidden target accesses must remain checked, while the strict closed-trace gate still requires actual advisory publication, accepted backend hit and real full-line L1 writes. This is a first-touch synthetic correctness control, with no general-application or performance claim. Increasing the evictor count or tuning replacement timing is unnecessary for this mechanism gate.

`localization.json` binds its exact replay script, complete selected-event input and five critical RTL sources, and binds the compiled pseudo-LRU encoder/decoder hashes to the consumed model's source list. `analyze_selected.py` is the replayed offline analysis source. The parent's unchanged run/admission records bind the raw waveform and model/ELF/NBF identities.
