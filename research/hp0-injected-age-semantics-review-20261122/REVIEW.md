The common HP0 shim delays each accepted response beat by a minimum age N. It does **not** start a timer at AR acceptance, first incoming RVALID, or receipt of the full burst. Consequently N40/N200 are added response-age controls, not absolute physical DDR request latencies. This review reads existing source and closed reports only; it runs no model, reader, compiler, vendor tool, board command or cleanup.

Source basis is the audited TOP eb7d390134a0025331a2366a979a774263b146d5 / BP8dfdbdeec84cb47f902bc1426d69ecb3efd91c7c canonical1792 controls. `evidence.json` pins all inspected source/report bytes. Static comparison confirms the current inspected shim and both FIFO files are byte-identical to the preserved native, N40 and N200 audit snapshots. This does not transfer those historical models' qualification to current CSR/borrowing hardware.

The paths below are relative to `/home/coyang/zynq-parrot-linux-capacity` unless absolute.

### Timer and endpoint equations

`cosim/black-parrot-example/v/bp_axi_response_delay_fifo.sv:34,40–47,57–59,74–81` timestamps `{cycle_i,payload_i}` when `push = v_i && ready_o`. Each FIFO head becomes eligible when its elapsed enqueue age reaches N. Its eligible flag stays set through downstream backpressure. There is no AR input or burst-completion timer. The same mechanism handles R and B independently (`bp_axi_response_delay.sv:73–86`).

For N>0, use edge-sampled integer cycles, in the continuously running transaction domain without a reset or ambiguous full counter-period wait. Let A be a particular read's accepted AR, u[k] the shim's acceptance of its R beat k, f[k] its first BP-facing output offer, and a[k] its BP-facing acceptance. Index previous beats in the **whole R stream**, including preceding bursts/IDs. The FIFO preserves their order:

```
f[k] = max(u[k] + N, a[previous-stream-beat] + 1)
a[k] = earliest cycle t >= f[k] with BP RREADY(t)
```

For the first stream entry, omit the previous-beat term. The head/next forwarding avoids an additional per-word bubble; the equations describe accepted rising edges, not a subcycle combinational transition. The 32-bit enqueue-age subtraction handles ordinary cycle wrap; once a head is eligible, its VALID does not fall even during prolonged backpressure. These equations do not claim an exact maximum delay after an ambiguous multiple-wrap queue residence.

Writing H[k] for additional preceding-stream head-of-line delay and S[k] for that beat's offered-to-accepted stall:

```
AR -> first offered  = (u[0] - A) + N + H[0]
AR -> first accepted = (u[0] - A) + N + H[0] + S[0]
AR -> full offered   = (u[last] - A) + N + H[last]
AR -> full accepted  = (u[last] - A) + N + H[last] + S[last]
```

Here u includes upstream memory/interconnect service and any shim input stall. An upstream first RVALID offer that stalls is **earlier than u** and does not start the shim timer. Gaps between incoming beats remain in u; downstream stalls and earlier queued responses can add further delay. With no stalls/earlier obstruction and a B-beat burst arriving at one beat/cycle, if upstream AR-to-first accepted R is L, BP-facing first/full are L+N and L+(B−1)+N. N is added once to the shifted stream, not B times. It is neither `max(L,N)` nor a timer restarted after each output word.

The analogous B equation is `AW -> BP-B = (uB−AW)+N+HB+SB`; measured from accepted WLAST, replace AW with WLAST. AW/W themselves are not delayed by this shim. Delaying B can prolong upstream ordering ownership and later request issuance.

N0 is a separate compile-time branch in `top_zynq.sv:220–228`: VALID, every payload field, and READY are direct wires, with no delay instance. N>0 uses the FIFO branch at229–258. Thus N>0 also decouples upstream/downstream READY until the queue fills. Even with unchanged address-channel wiring, later requests and upstream response acceptance can differ between runs; a universal cross-run identity “physical total latency increases exactly N” is unwarranted without matched observed endpoints.

### Bandwidth and concurrency

The positive branch instantiates separate512-entry R and B queues, a shared response clock `aclk`, and fixed reset delay; runtime configuration is tied off (`top_zynq.sv:236–255`). Both queues can accept and deliver concurrently at one beat per channel per clock. R is64b here: peak shim output bandwidth is8 bytes/core cycle, conditionally160MB/s at20MHz, not a physical DDR throughput measurement. No ID-specific parallel output lanes exist; all R IDs share FIFO order and can suffer head-of-line blocking. Full512-entry rings backpressure input; simultaneous pop permits replacement (`fifo.sv:44–47`). R/B queues do not impose mutual read/write serialization. The reset is `~aresetn`, not CPU/tag-stop reset; no live reset/drain inference is justified.

The allocating bridge is not restricted to one outstanding read merely because the fixture observed one. `bp_axi_top.sv:325–335` passes `num_cache_p=num_cce_p*l2_dmas_p`, eight64b beats and ordering enabled. The canonical static16KiB configuration has two DMA interfaces/two read-tag slots, independently confirmed in the closed `research/hp0-closed-trace-20261121/pf-localization02/README.md` and `lower-gate03/gate.json`. `bsg_cache_to_axi.sv:19–21,107–167` has separate read/write arbiters and tag capacity equal to the interface count. `bsg_cache_to_axi_rx.sv:77–110,171–182` consumes a tag at accepted AR and retires it after the line's final DMA word; ARID is0. The independent ordering CAMs cap outstanding addresses, prohibit opposite-channel same-line hazards, and clear after accepted RLAST/B (`bsg_cache_to_axi_ordering.sv:59–64,94–101,129–164`). Their clearing cycle can also fence issuance. These are source limits; they are not evidence that a workload achieves two concurrent reads or the independent upper envelopes simultaneously. AXI W is one noninterleaved stream and BREADY is tied1 (`tx.sv:273`).

Closed canonical whole-core audits observed maximum one read and one write separately, with no queue/full/input/downstream stalls; earlier closed08/10 common-path audit explicitly observes overlapping read/write requests and combined peak2. Source supports independent R/B handling; the particular target predecessor/PF pairs had **no overlapping write**. Do not infer a one-total-transaction architecture limit or saturated bandwidth from those fixtures.

### Which requests share the setting

`top_zynq.sv:191–217,244–251` puts the shim on the sole HP0 R/B return before the processor's ordinary/prefetch demultiplexing. All demand-I, demand-D, proactive-I and proactive-D responses that actually miss down to HP0 traverse it. Retained/L1/L2 hits, GP0 registers and other ports are outside the delay. Normal write completions traverse B.

For retention builds direct prefetch AXI bypass is rejected. In `bp_unicore.sv:191–198,225–242,405–423`, disabling bypass routes D prefetch through the same L2 destination as ordinary nonlocal memory; I traffic is likewise ordinary allocating traffic. `bp_axi_top.sv:492–511` then has no separate prefetch AXI master/demux. All read IDs are normally0 (`rx.sv:100`); RID0 cannot distinguish I/D/demand/advisory. The top's `prefetch_outstanding_p(1)` describes the disabled alternate bypass master, not the active allocating path's retained-line capacity or measured concurrency. Historical bypass configurations must not be pooled with these controls.

The closed shared-pump localization explains why advisory admission-to-publication can increase by2N: in08/10 a preceding request's held L2 forward word delays the target's own AR by N, and the target response then ages by N. That trace had read-RR valid0/tag-ready1/fence0, so the observed hold was upstream of AXI credits, not exhaustion of the two bridge slots. This is a checked fixture dependency, not an exclusive application bottleneck or universal2N response law.

### What the existing controls actually establish

Canonical native/N40/N200 are TOPeb7d/BP8df, same static16KiB L2,1792 retained lines/side,256 sets and20MHz; models respectively b912913adc5fa98a0675bd323e7b37da7cbaecdabbb787ca3f466edcc4851de9, a183aa7f912ce5a7346672ab57470912b2eb8627800e31443a596360cf9ee803, and692d6430d08f31806214384604524d0753079c2e48a0ae837d6a950a4351265e. The closed N40/N200 summaries and native independent review preserve source/payload/endpoint checks, not inferred values.

| Measured simulation endpoint, core cycles | N0 | N40 | N200 |
|---|---:|---:|---:|
| External accepted AR→first/full accepted R |1/8|1/8|1/8|
| BP-facing accepted AR→first/full accepted R |1/8|41/48|201/208|
| Accepted intraburst R spacing |1|1|1|
| Each R/B beat input-accept→offer and accept age |0|40|200|

Each run audits648 reads/5184 R beats and487 B completions, preserving all ID/data/RESP/LAST fields and order **within that run**. R/B peaks are8/1 at positive N. Cross-run opaque traffic need not be identical because cycle-dependent data can change. N40/N200 target checks independently join all512 data bits to64 file-backed ELF bytes, retained publication and eight winning normal-L1 SRAM writes. Later retained ACK14/21 does not establish architectural load/fetch readiness. The controlled downstream1/8 transport is not physical calibration.

Do not conflate two older mechanisms: `bp_nonsynth_axi_mem_pipelined.sv:188–205` sets an absolute due time from **accepted AR**, and its older full-burst40/200 study reports that service setting. The common response shim instead timestamps **accepted R/B beats**, downstream of the existing responder. Their equal numbers do not make the models equivalent. Likewise the historical physical~41-cycle software dependent-load interval is neither40-cycle full-line service nor an HP0 first/full measurement.

At a verified20MHz response clock one cycle is50ns, hence N40/N200 correspond arithmetically to2/10 microseconds of per-beat minimum added queue age. Physical request-to-first/full would include actual AR-to-input-R service, burst gaps, queues and stalls. These figures are neither native DDR latency nor a calibrated high-frequency CPU; final positive-delay FPGA area/timing and matched instrumentation are separate gates.

### Existing physical observation and remaining measurement gaps

The existing eb7d physical observability review found no deployed AR→first/full recorder. GP0 retained hit/publication/SRAM-word counters measure mechanism use, not latency. Miss trace CSRs identify accepted L1 requests but omit advisory and HP0 first/LAST endpoints; L2 hits may produce no HP0 read. Positive-delay internal queue/age signals are trace-visible but not host-readable registers and are absent in N0. Existing FST audits can establish those endpoints only for their bound simulation model.

The already-frozen passive observer prototype73b4d74a3dff50e8674a321b36d1dfeaa395ac5b9e7d653c04f9ebd1fb29cfe5 has41 passing standalone directed cases. Its existing format records accepted AR address/ID/LEN/SIZE/BURST/sequence, first/full offered and accepted ages, beats/stalls, errors/write-overlap and overwrite coverage. It keeps16 windows, invalidates overlapping reads, and freezes only after drain with a final-record read guard/held index echo. It is **not** qualified fitted/deployed evidence. It carries no source-role or data-integrity discriminator.

The minimum unresolved measurement prerequisites are therefore existing diagnostic-image integration/physical area+timing qualification, checked freeze/index/echo readout, and complete expected AR sequence/records including invalid/gaps/saturation. Source roles need independent phase/address/request association upstream of shared RID0 and proof of actual HP0 passage; an L2 hit cannot be assigned a fictitious DDR latency. An external-only tap can measure physical memory-side service, but cannot by itself establish positive shim input→output age; that needs both existing signal sides observed in the exact diagnostic configuration. Arbitrary overlapping mixed-application I/D/PF attribution and CPU-ready timing remain outside this isolated-window observer. This review proposes no new RTL or acquisition experiment.
