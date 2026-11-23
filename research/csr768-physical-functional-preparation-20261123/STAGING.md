This is the shortest local staging and collector handoff for the actual selected96KiB image. It binds existing bytes without approving TAG STA, deployment or board execution. ROOT runs these commands only inside the funded16MiB physical family after its source/resource review; this agent has not copied, extracted or uploaded anything.

`admission.bound-inputs.DRAFT.json` resolves private9c/rollback2dd/compile4ed7, MAX1792 ELF062a/manifest88546,33 current runtime source hashes, selected package44d0/BITd302/HWHf40b/MAPcc43 and the full original RAM audit rows exported by ROOT. The13k actual-shapes export is provenance, not a substitute for the full4.27MB audits. `model-completion.DRAFT.json` supplies the exact current model/all-three-role envelope for ROOT promotion, with ROOT_verified false. Fit, TAG STA, elaboration, approvals and board/resource authority remain NULL. Never pass a DRAFT to --execute.

RollbackBIT is the existing loose accepted-f744.bit. RollbackMAP can reference the byte-identical selected81-byteMAP. The matching oldHWH9c4d36 exists in local package07a48584 as `black_parrot_bd_1.hwh`, with exact member SHA/size independently retained by the closed historical stage-v2 receipt. Only its loose materialization is pending. The following commands prepare three unchanged NBF names plus that HWH,8,235,141B in total, without touching any source/model or board file:

```bash
P=/home/coyang/fpga-artifacts/context-resume/csr768-physical-functional-20261123/inputs01
B=/home/coyang/fpga-artifacts/context-resume/retained-capacity1792-fixtures-20261121/preparation01/build01
mkdir -p -m700 "$P"
cp --no-clobber -- "$B/d-enabled/prog.nbf" "$P/retained-capacity768-d-enabled.nbf"
cp --no-clobber -- "$B/d-off/prog.nbf" "$P/retained-capacity768-d-off.nbf"
cp --no-clobber -- "$B/i-enabled/prog.nbf" "$P/retained-capacity768-i-enabled.nbf"
python3 -B - <<'PY'
from pathlib import Path
import base64,hashlib,io,tarfile
source=Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/fpga-fit/20261120T211416Z-7edf64d1/black_parrot_bd_1.zynq.pynqz2.tar.xz.b64')
raw=source.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='07a48584e22de3e1d97cdaef16d27a92faabc1a9f3db82bafd5e76fe18f1bbe5'
with tarfile.open(fileobj=io.BytesIO(base64.b64decode(raw)),mode='r:xz')as tar:
    member=tar.getmember('black_parrot_bd_1.hwh')
    assert member.isfile()and member.size==311517
    data=tar.extractfile(member).read()
assert hashlib.sha256(data).hexdigest()=='9c4d36c5a576a861e4732ee14b78e58fc96d29a60a71c78f04d2312c1bf8c2fb'
with Path('/home/coyang/fpga-artifacts/context-resume/csr768-physical-functional-20261123/inputs01/rollback-f744.hwh').open('xb')as output:
    output.write(data)
PY
```

ROOT then verifies the four staged file bindings already declared in `pending_local_staging`, promotes the actual model-completion and image/fit/TAGSTA/elaboration/io_contract certificates, writes the small approvals.ROOT.json, and creates an EXTERNAL reviewed admission with exact source hashes. The entire source/metadata prefix is prospectively bounded128KiB for this concrete handoff (no guest/output cap change). All new local outputs, including subsequent collector logs and source snapshots, stay charged to the funded16MiB physical family.

After actual TAG STA and image/board/source/funding approvals, the existing collector performs all uploads, atomic install, fresh reset per case and recovery while holding the existing common lock:

```bash
H=/home/coyang/zynq-parrot-retained-metadata/research/csr768-physical-functional-preparation-20261123
python3 -B "$H/collector.py" REVIEWED768.json
python3 -B "$H/collector.py" REVIEWED768.json --execute /home/coyang/fpga-artifacts/context-resume/csr768-physical-functional-20261123/session01
```

Use the safe present→fixed→COST pilot commands already in README immediately after the actual recovered capacity result and exact same image/API bindings. Applications use accepted2dd/de54 and the deployed46MiB contract. No new kernel witness, joint workload, hardware build or native matrix is inserted. The current rollback inventory reports52,948,992B available remotely; the maintained stage collector must remeasure and enforce its full package/NBF/rollback/runner peak plus16MiB spare before any board write, rather than trusting this stale snapshot.
