This note preserves the first directed retention-policy run and explains its failed assertion. It is a harness diagnostic, not a hardware failure or acceptance result.

The mode-2 33rd-line case reused a helper that unconditionally expected retention whenever capture was enabled. Modes 0 and 1 passed; mode 2 correctly declined the 33rd line, triggering the old expectation. The helper now accepts an explicit expected admission value for this capacity case; the original build log, failed run log, and FST remain in runtime-policy/. No RTL change was made for this failure.
