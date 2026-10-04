# Minimal final-switch fallthrough probe

This experiment starts from the failing 64-byte-aligned control and changes
exactly one instruction in each peer function's normally unreachable terminal
path. It inserts one `nop` immediately after the peer's final `csrwi 0x800, 0`
and before the self-loop. The original C verification, stack layout, source and
peer addresses, and ordinary demand-loop instructions remain unchanged.

The preceding stale-terminal probe completed 640 launches without ever
executing its architectural terminal marker. This minimal control tests whether
the instruction immediately following the switch affects the switch pipeline
before redirection completes.

The exact binary (`34fac3922b0bf19669795d0c10169c6a00e440ee051e375b163d51967f119c99`)
completed samples 1--4 and then stopped returning during sample 5. The controller
observed 60 seconds without further output and stopped the run; the board was
subsequently recovered before any other measurement. Because the extra `nop`
did not prevent the failure at `0x11e80`/`0x11ec0`, immediate fallthrough into
the terminal self-loop is not the cause.
