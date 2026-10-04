# Stale peer terminal-PC probe

This diagnostic tests whether a later hardware-demand sample sometimes resumes
context 1 at the preceding sample's terminal parking loop instead of at the
newly seeded `peer_demand` entry.

It starts from the 64-byte-aligned control. The ordinary source and peer demand
loop instructions are unchanged. Only the peer's normally unreachable code
after its final switch is changed: if execution returns there, it writes the
unique terminal marker `2` into the existing completion record and repeatedly
switches back to context 0. The C failure path reports the marker and exits
directly, allowing the physical run to retain the diagnosis.

The exact binary (`f55a7f495672c68d0fb27d0e9a41f87b926dfca44fd743cdbd76e55bbc5b3228`)
completed 128 launches after one fresh boot and another 512 after a second fresh
boot. All 5,242,880 requests passed, both runs ended with request exit 0 and
`CORE[0] PASS`, and the terminal marker never appeared. The medians were 611,415
and 612,097 cycles per 8,192-request sample. This is evidence against resuming a
parked context at the stale terminal PC, although this diagnostic also occupied
the passing `0x11f00`/`0x11f40` placement.
