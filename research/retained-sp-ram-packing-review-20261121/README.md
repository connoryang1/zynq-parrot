This independently verifies the closed five-geometry RAM-only batch and preserves its source, reports, primitive/clock records and bounded acquisition receipt. It launches no tools or remote operations. The result guides a capacity candidate; it does not establish full-core correctness, production timing or whole-device fit.

The exact parameter and owning-clock storage slices match frozen SPd766 and metadata19bd byte-for-byte. The wrapper retains their original local address subtraction/casts, read-first output registers and enables, with all RAM controls/addresses/data variable and registered read outputs observed. It excludes the FSM, epoch/RR metadata arrays,512-bit line buffers and CPU/UCE. Each lane owns its own RAM arrays; every mapped RAM primitive has only its lane's active clock port. The extracted tag record is29bits (valid+8epoch+20physical tag), each line has eight64-bit payload words, and each side uses256sets.

| Lines per side | Payload per side | Payload tiles, both sides | Tag tiles | Total tiles | Logic LUT | FF |
| --- | --- | --- | --- | --- | --- | --- |
|1280|80KiB|37|4|41|149|6|
|1536|96KiB|44|4|48|147|4|
|1792|112KiB|52|4|56|278|6|
|1856|116KiB|56|4|60|287|8|
|1920|120KiB|56|4|60|285|8|

These are actual Vivado2024.2 Default-directive mappings with eight threads and unchanged global_retiming/control-set options. **The50ns lane clocks and asynchronous clock groups are created after synth_design.** They support primitive port ownership reporting, not a claim that synthesis or retiming used production clock constraints. No timing/routing report or application execution is part of this batch. RAM-only counts are not additive to whole-CPU utilization.

All six acquisition commands returned0: admission, upload, the single fixed600s synthesis batch, terminal no-orphans, closed-file inventory, and collection. SSH allowed640s; no retries or extensions occurred. Every collected artifact matches the remote closed inventory. All five DCP ZIPs pass integrity checks and remain external/hash-bound; compact source, five reports, complete primitive censuses, RAM port/clock records and logs are archived losslessly here.

Root selected1792lines per side (224KiB total configured retained payload) for a later full-core and routed gate. That is a candidate choice, not a fit or usefulness result. This review does not read that subsequent active preparation. Run `python3 -B research/retained-sp-ram-packing-review-20261121/close.py` to reverify the closed source, report, primitive, receipt and archive bindings.
