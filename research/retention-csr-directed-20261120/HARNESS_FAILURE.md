This note records an initial CSR test build setup failure. No simulation result came from this attempt.

The new BE component test omitted HardFloat include directories required by the shared BE defines header; the build log identifies the two missing .vi files. The runner now supplies the exact pinned local HardFloat source/RISCV includes.
