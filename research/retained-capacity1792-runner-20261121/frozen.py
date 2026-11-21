"""Content-pin the unchanged foundation before importing its common validator."""
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
FIXTURE=Path('/home/coyang/zynq-parrot-retained-observation/testing/rtl/retained-capacity-fixture')
def verify():
 rows=json.loads((HERE/'frozen-foundation.json').read_text())
 for r in rows:
  raw=Path(r['path']).read_bytes()
  if len(raw)!=r['bytes'] or hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('frozen foundation drift '+r['path'])
 return rows
verify()
sys.path.insert(0,str(FIXTURE))
