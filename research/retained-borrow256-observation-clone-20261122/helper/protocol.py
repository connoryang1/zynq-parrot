"""Exact unchanged cold08 completion/GP0 protocol; no target execution."""
import importlib.util
import re
from common import SP,require

PASS='[BSG-PASS] retained advisory full-line I/D checked all words completed'
COUNTERS=(r'RETAINED_USE_COUNTERS version=1 i_hits=(\d+) d_hits=(\d+) '
          r'i_published=(\d+) d_published=(\d+) i_write_beats=(\d+) d_write_beats=(\d+) '
          r'saturating_bits=16 reset=axi_only')


def parse(text,returncode):
    spec=importlib.util.spec_from_file_location('SP_checker',SP/'testing/check_run.py')
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    checker.check_transcript(text,returncode)
    require(text.count(PASS)==1 and text.index(PASS)<checker.CORE_PASS.search(text).start(),
            'missing/ordered checked cold08 return')
    rows=re.findall(COUNTERS,text)
    require(len(rows)==1 and tuple(map(int,rows[0]))==(1,1,1,1,8,8),'wrong actual GP0 observer words')
    protocol=[l for l in text.replace('\r','').splitlines() if l==PASS or
       'CORE PASS' in l or 'RETAINED_USE_COUNTERS' in l or 'Returning from ps_main with RC:' in l or
       l.endswith('BSG PASS') or 'minstret' in l or 'MTIME start:' in l or 'MTIME stop:' in l or 'MTIME delta ' in l]
    return dict(counter_values=list(rows[0]),protocol_rows=protocol,returncode=returncode)
