# seL4 protected-RPC V2 fault gate

The retained `full-system-fresh-model.log.gz` is the accepted fault-only seL4
simulation.  It uses a freshly rebuilt two-thread/four-context Verilator model
from BlackParrot `7ad23b7c697e75b3519f19ffb41884210dc3f823` and reaches the exact
`SEL4IPCRPC0002` pass marker.

- Model SHA-256: `e5c1e823423b202368b33c66565210371b42d566b5c6d1b2ff922fe862701651`
- NBF SHA-256: `81ebb02c94127f2008164d1482c8a7c0a69bf0b2461f385efaee659b5b624fd2`
- Log SHA-256: `698ddbc06ed5def8be39275eef94aff2073929cbed189e62556a391cba94febf`
- Compressed log SHA-256: `2c834e0f9829494ec54de5308b7d07cbe826940b5ccc85480c84afb12e1605d6`

The strict checker accepts the region guard, server-fault completion,
terminal retry, privileged record consumption, fresh rebind, normal call, and
final test verdict.  The known post-PASS DPI GPIO teardown assertion is not
part of this run because the runner stops on the exact seL4 pass marker.

The same NBF also passes on the physical PYNQ-Z2 using the timing-clean routed
package.  The serialized foreground runner reports the exact test verdict,
`CORE PASS`, `BSG PASS`, and exit zero; the strict physical checker accepts the
retained `physical-pynqz2.log.gz`.

- Package SHA-256: `3ea7effc89402c40ba12951f47ed03b8f95729ef8269e8317741cced17ec5b5d`
- Bitstream SHA-256: `c9cd7006d8501d25cf7981f16a2757c0b13461212b6cca4973163994f1da81f2`
- NBF SHA-256: `81ebb02c94127f2008164d1482c8a7c0a69bf0b2461f385efaee659b5b624fd2`
- Runner SHA-256: `2dd9c411614af25025b0b3770fba133c35f3652ad0fa6bf51786a3754a217c30`
- Physical log SHA-256: `e78b6643f4ca2c28344237b782c6f1c1d753d9a1fca57da2a070566c40d49498`
- Compressed physical log SHA-256: `7780975d18136c4220d829adefa2f77c4f8813fbf73d9807570e2e55d46d57f3`
- Retired instructions: `8,767,887` measured delta
- MTIME delta: `8,268,978` eighth-cycle ticks
- Host wall time: `1,653,818,797 ns`

An earlier run used a different model binary (`5c059f5e...`) and stopped on
the wide-write assertion.  Because it was not the freshly rebuilt model above,
it is not evidence against the `7ad23b7c6` arbitration fix.
