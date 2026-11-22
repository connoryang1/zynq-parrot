"""Pure expected-configuration predicates; no filesystem, network or tools."""
import re
from decimal import Decimal

PROJECTS=('top_ip_proj','black_parrot_bd_proj','tmp_edit_project')

def actual_defines(text,expected):
    return {key:sorted(set(int(v) for v in re.findall(r'(?<![A-Za-z0-9_])'+re.escape(key)+r'\s*=\s*(\d+)(?=$|[\s}\]";])',text))) for key in expected}

def contexts(text,expected):
    seen={key:[] for key in PROJECTS}
    for line in text.splitlines():
        match=re.fullmatch(r'BP-EXPERIMENT-CONFIG: project=(\S+) effective=(.*)',line.strip())
        if match and match[1] in seen:seen[match[1]].append(actual_defines(match[2],expected))
    return dict(actual=seen,complete=all(seen.values()),valid=all(rows and all(all(row[k]==[v] for k,v in expected.items()) for row in rows) for rows in seen.values()))

def clock_values(text):
    values={name:[] for name in ('CLKOUT1_REQUESTED_OUT_FREQ','CLKOUT2_REQUESTED_OUT_FREQ')}
    for name in values:
        for value in re.findall(r'"'+name+r'"\s*:\s*\[\s*\{\s*"value"\s*:\s*"([^\"]+)"',text):
            values[name].append(str(Decimal(value).normalize()))
    return values

def clock_match(text):
    values=clock_values(text)
    return dict(actual=values,valid=bool(values['CLKOUT1_REQUESTED_OUT_FREQ'] and values['CLKOUT2_REQUESTED_OUT_FREQ'])
        and all(Decimal(v)==20 for v in values['CLKOUT1_REQUESTED_OUT_FREQ']) and all(Decimal(v)==8 for v in values['CLKOUT2_REQUESTED_OUT_FREQ']))

def clean_script(text):
    # OOC IP checkpoints are allowed; whole-design incremental seed commands
    # are outside this clean admission. Comments/echoed source are excluded.
    lines=[line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    for line in lines:
        if re.search(r'\bread_checkpoint\s+[^\n]*-incremental\b',line,re.I):return False
        if re.search(r'\bset_property\s+incremental_checkpoint\b',line,re.I) and not re.search(r'incremental_checkpoint\s+(?:\{\}|"")\s',line,re.I):return False
    return True


def vendor_process(row):
    # Deliberately conservative, including inert real-basename fixtures. Never
    # infer permission to signal a foreign process from this classifier.
    names={'vivado','vivado_lab','xvlog','xelab','xsim','xsimk','launch_synthesis.sh','run_vivado_2024_2.sh','vivado_synth_wrap.sh','vivado_impl_wrap.sh'}
    return row.get('state')!='Z' and (row.get('comm') in names or any(token.rsplit('/',1)[-1] in names for token in row.get('argv_tokens',[])))
