This checkpoint preserves a matched Default opt/place comparison of the existing CSR snapshot component DCPs. It asks whether the source-proven single-write, resetless-RAM organization can reduce occupied component slices before any integrated qualification. It does not establish whole-CPU headroom, timing closure, physical behavior, or application benefit.

| Actual occupied sites | Original reset-FF baseline | Unmasked production-contract RAM |
|---|---:|---:|
| SLICEL | 1,441 | 714 |
| SLICEM | 812 | 452 |
| Total occupied slices | 2,253 | 1,166 |
| Post-place setup WNS (ns) | 44.123 | 44.245 |
| Setup TNS (ns) | 0 | 0 |
| **Pre-route hold WHS (ns)** | **−0.317** | **−0.139** |
| Hold failing endpoints | 7,213 | 198 |
| Hold THS (ns) | −673.213 | −5.090 |

Both arms returned native0, source end checks passed, and owned groups were gone with the ROOT claim RELEASED. Total acquisition elapsed158.401s. The slice counts are unique actual placed sites, deduplicating memory macro/leaf overlap. Both used the same otherwise empty out-of-context xc7z020 device,50ns owning clock/0nsIO, two threads and Default opt/place; no RTL elaboration, synthesis, phys_opt or routing ran. These are estimated pre-route timing reports; **hold timing is negative for both, so timing is not closed**. Do not subtract the1,087-component-slice difference from a whole-CPU result.

Inputs were exact post-synthesis04baseline and05unmasked DCPs. The unmasked variant changes only invalid raw payload semantics under the already-proved consumer selection; it has no accepted integration or fullcore result. Previous synthesis was4178total LUT/6668FF for baseline versus4459total LUT(3347logic+1112LUTRAM)/4FF for unmasked. Thus totalLUT grew281 even though logicLUT fell831 and FF fell6664. Default component placement can exploit those different packing types; their interaction with a real CPU and routed timing remains unmeasured. Actual mapped functional qualification is a separate outstanding prerequisite, and this checkpoint does not promote its pending/failed wrappers.

source/ contains exact executed helpers, DRAFT and FINAL admissions. proof/ contains the actual ROOT release/resource records, full closed manifest/session, slice summaries and lossless-gzip timing/utilization/control-set reports. results.json binds every original and stored byte. Original raw placed DCPs/all reports are retained externally in the independently round-tripped6,072,204B archive named by the manifest; no model/checkpoint/raw archive is copied into Git. The external manifest SHA isdbe2fa8b2bc664190fb9a85ad6afd9ae74fa7dd891d9064d7cb34a39e3fa9395.

The source helpers retain their historical absolute paths for exact reproduction; rerunning requires a fresh ROOT admission/global resource and vendor ownership review, not the old one-shot paths. No board or whole-device CAD action is authorized by this checkpoint. Main capacity-bisection source and cache/thread/context geometry remain unchanged.
