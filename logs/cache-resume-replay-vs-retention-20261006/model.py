#!/usr/bin/env python3
import hashlib, json, math
from pathlib import Path

root=Path(__file__).resolve().parents[2]
replay_path=root/'logs/linux-post-resume-replay-20261002/cost-results.json'
sched_path=root/'logs/linux-scheduler-resume-20261002/results.json'
replay=json.loads(replay_path.read_text())
sched=json.loads(sched_path.read_text())

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
# Extract accepted medians from the retained parser output.
points={}
for key in ('8k','10k','12k'):
    d=replay['derived'][key]
    points[d['lines']]={
      'replay_cycles_one_side':d['replay_cost_cycles'],
      'linux_resume_cycles':d['same_run_resume_cycles'],
    }

clock_hz=18_000_000
cache_bytes=32*1024
line_bytes=64
sets=64
ways=8
contexts=2
address_metadata_bits=32
logical_contexts=10
bram18_bits=18*1024
rows=[]
for lines,d in points.items():
    combined_bytes=2*lines*line_bytes
    serial_combined=2*d['replay_cycles_one_side']
    slack=d['linux_resume_cycles']
    required_rate_multiplier=serial_combined/slack
    required_bytes_per_second=combined_bytes/(slack/clock_hz)
    ways_per_context=lines/sets
    total_reserved_ways=contexts*ways_per_context
    history_bits_per_context=2*lines*address_metadata_bits
    history_bits_ten=logical_contexts*history_bits_per_context
    rows.append({
      'lines_each_instruction_and_data':lines,
      'combined_replay_bytes':combined_bytes,
      'serial_combined_replay_cycles':serial_combined,
      'measured_linux_resume_slack_cycles':slack,
      'rate_multiplier_over_serial_needed_to_fit_slack':required_rate_multiplier,
      'required_effective_megabytes_per_second_decimal':required_bytes_per_second/1e6,
      'retention_ways_per_context_per_cache':ways_per_context,
      'two_context_reserved_ways_per_cache':total_reserved_ways,
      'ways_left_unreserved_per_cache':ways-total_reserved_ways,
      'address_history_bytes_per_context':history_bits_per_context/8,
      'ten_context_history_bram18_raw_minimum':math.ceil(history_bits_ten/bram18_bits),
    })
out={
 'method':'Use accepted physical serial replay costs and same-run Linux resume medians to compute the concurrency required for combined I+D background replay. Map 128/160/192 64-byte lines onto the measured 32-KiB, 64-set, 8-way I/D caches for a two-resident-context retention alternative. Address-history storage assumes 32 bits per remembered line including minimal metadata.',
 'inputs':{str(replay_path.relative_to(root)):sha(replay_path),str(sched_path.relative_to(root)):sha(sched_path)},
 'fixed':{'clock_hz':clock_hz,'cache_bytes_each':cache_bytes,'line_bytes':line_bytes,'sets':sets,'ways':ways,'resident_contexts':contexts,'logical_contexts':logical_contexts,'history_bits_per_line':address_metadata_bits},
 'rows':rows,
 'conclusion':{
  'linux_scheduler':'At the 160-line middle point, combined I+D replay needs only 1.24x the measured serial replay rate (32.5 MB/s) to fit inside the existing 11.35k-cycle Linux resume interval.',
  'fast_hardware_handoff':'A 5-11-cycle handoff cannot hide thousands of cycles of large replay; resident-context retention is required for immediate hot state, with a small signature useful only as a complement.',
  'capacity':'For two resident contexts, 128/160/192 retained lines per context consume 4/5/6 of eight ways in each cache, leaving 4/3/2 ways unreserved. Ten simultaneous retained contexts cannot fit.',
  'hybrid':'Use retention or partitioning for resident contexts, background replay for nonresident or ordinarily scheduled contexts, and the depth-two signature for first-touch assistance.',
 },
 'limits':[
  'This is an accounting model, not a concurrent replay or retention measurement.',
  'Instruction and data replay may contend with scheduler traffic and with each other.',
  'Strict 160-line retention is 2.5 ways per context and requires skewed/set-selective allocation rather than a uniform integer-way partition.',
  'Refill-equivalent line counts are sizing guides, not exact unique line histories.',
  'History storage excludes banking, ECC, generation tags, replacement state, and ports.',
 ]
}
path=Path(__file__).with_name('results.json'); path.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
