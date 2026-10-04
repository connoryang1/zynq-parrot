# Original logic at the probe's passing addresses

This control starts from the failing 64-byte-aligned source and changes only
the source hardware-loop alignment from 64 to 256 bytes. This places
`source_demand` at `0x11f00` and `peer_demand` at `0x11f40`, exactly matching
the stale-terminal probe that completed 640 launches across two fresh boots.

Unlike that probe, this build retains the original peer parking loop, original
C verification, and original stack layout. A sustained pass would isolate the
effect to absolute code placement; a failure would show that another probe
change caused its stability.

The exact binary (`e62165fadea93925860848bb7642ec2a83c1d10ff38ab6404ec26b48480dcd72`)
completed all 512 fresh-boot launches: 4,194,304 checked requests, request exit 0,
and `CORE[0] PASS`. The median was 612,178 cycles per 8,192-request sample
(74.729 cycles/request), with a 588,915-cycle minimum and 651,217-cycle maximum.
This shows that absolute PC placement alone is sufficient to remove the observed
failure in the unmodified switching loop; it does not by itself prove which
PC-indexed frontend structure is responsible.
