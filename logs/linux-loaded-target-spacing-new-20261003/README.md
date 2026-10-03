This recoverable probe checks load-to-context-switch target selection on the routed fifth-dependency-stage candidate. Correct target 1 and stale target 2 share a return stub, allowing the selected context to be observed from zero through eight bubbles.

A first run with target 1 initially resident passed every spacing, including adjacent `load; CSR800`; its ELF SHA-256 was `8fd1a58441aca99c50e96c3c74f49e6305d5745ddb62cb5767dbaa510f8284eb`. A second run first switched through context 2 to evict target 1 before every case; it also passed every spacing with exact ELF SHA-256 `2dae8f593d3d9dafc59dcfd3adf91f0a3a6301016ad454e00684558b22e5131e`.

Both runs used candidate bitstream SHA-256 `84ea265f3fc33c2647a1afd20fc523d3da466019fafcc835f512047410a4c38d`, passed guest hash and native exit checks, and ended in `CORE[0] PASS`. These one-shot passes do not qualify the candidate because sustained loaded-target switching fails separately.
