# Stream a BlackParrot VCD (normally ``fst2vcd dump.fst``) and preserve just
# SATP transitions plus the final retired instructions.  GNU awk is used here
# deliberately: VCD value changes can exceed a Python per-line parser's
# practical turnaround time even for a small compressed FST.
#
# Usage:
#   fst2vcd dump.fst | awk -v tail=128 -f tools/satp_fst_tail.awk

function bhex(bits,    i, nibble, value, result, digit) {
  if (bits == "" || bits ~ /[^01]/)
    return "x"
  result = ""
  while (length(bits) % 4)
    bits = "0" bits
  for (i = 1; i <= length(bits); i += 4) {
    nibble = substr(bits, i, 4)
    value = 0
    value += substr(nibble, 1, 1) * 8
    value += substr(nibble, 2, 1) * 4
    value += substr(nibble, 3, 1) * 2
    value += substr(nibble, 4, 1)
    digit = substr("0123456789abcdef", value + 1, 1)
    result = result digit
  }
  sub(/^0+/, "", result)
  return "0x" (result == "" ? "0" : result)
}

function remember_commit(    slot, record) {
  if (instret != "1") {
    last_commit = ""
    return
  }
  record = cycle " pc=" bhex(pc) " vaddr=" bhex(vaddr) " trans_en=" bhex(trans_en)
  if (record == last_commit)
    return
  last_commit = record
  slot = (++commit_count - 1) % tail + 1
  commits[slot] = record
}

function remember_satp(bank, mode, ppn, write, addr, data,    state, event) {
  state = mode SUBSEP ppn
  if (state != satp_state[bank]) {
    satp_events[++satp_count] = "cycle=" cycle " bank=" bank " satp mode=" bhex(mode) " ppn=" bhex(ppn)
    satp_state[bank] = state
  }
  event = write SUBSEP addr SUBSEP data
  if (event != satp_write_state[bank] && write == "1" && bhex(addr) == "0x180")
    satp_events[++satp_count] = "cycle=" cycle " bank=" bank " satp_write data=" bhex(data)
  satp_write_state[bank] = event
}

function sample() {
  if (!dirty)
    return
  cycle = int(current_time / period)
  remember_commit()
  remember_satp(0, csr0_mode, csr0_ppn, csr0_w, csr0_addr, csr0_data)
  remember_satp(1, csr1_mode, csr1_ppn, csr1_w, csr1_addr, csr1_data)
  dirty = 0
}

function emit() {
  print "SATP EVENTS"
  for (i = 1; i <= satp_count; i++)
    print satp_events[i]
  print "FINAL COMMITS"
  first = commit_count > tail ? commit_count - tail + 1 : 1
  for (i = first; i <= commit_count; i++)
    print commits[(i - 1) % tail + 1]
}

BEGIN {
  period = period ? period : 50000
  tail = tail ? tail : 32
  depth = 0
  header = 1
}

header && $1 == "$scope" {
  scope[++depth] = $3
  next
}

header && $1 == "$upscope" {
  delete scope[depth--]
  next
}

header && $1 == "$var" {
  code = $4
  full = ""
  for (i = 1; i <= depth; i++)
    full = full "." scope[i]
  full = full "." $5
  if (full ~ /be\.calculator\.commit_pkt_cast_o\.pc$/) c_pc = code
  else if (full ~ /be\.calculator\.commit_pkt_cast_o\.vaddr$/) c_vaddr = code
  else if (full ~ /be\.calculator\.commit_pkt_cast_o\.instret$/) c_instret = code
  else if (full ~ /gen_csr\[0\]\.csr_inst\.csr_w_v_li$/) c_csr0_w = code
  else if (full ~ /gen_csr\[0\]\.csr_inst\.csr_addr_li$/) c_csr0_addr = code
  else if (full ~ /gen_csr\[0\]\.csr_inst\.csr_data_li$/) c_csr0_data = code
  else if (full ~ /gen_csr\[0\]\.csr_inst\.satp_lo\.mode$/) c_csr0_mode = code
  else if (full ~ /gen_csr\[0\]\.csr_inst\.satp_lo\.ppn$/) c_csr0_ppn = code
  else if (full ~ /gen_csr\[1\]\.csr_inst\.csr_w_v_li$/) c_csr1_w = code
  else if (full ~ /gen_csr\[1\]\.csr_inst\.csr_addr_li$/) c_csr1_addr = code
  else if (full ~ /gen_csr\[1\]\.csr_inst\.csr_data_li$/) c_csr1_data = code
  else if (full ~ /gen_csr\[1\]\.csr_inst\.satp_lo\.mode$/) c_csr1_mode = code
  else if (full ~ /gen_csr\[1\]\.csr_inst\.satp_lo\.ppn$/) c_csr1_ppn = code
  next
}

header && $1 == "$enddefinitions" {
  header = 0
  next
}

header { next }

substr($0, 1, 1) == "#" {
  sample()
  current_time = substr($0, 2)
  if (max_cycle && int(current_time / period) > max_cycle) {
    emitted = 1
    emit()
    exit
  }
  next
}

substr($0, 1, 1) == "b" || substr($0, 1, 1) == "B" {
  value = substr($1, 2)
  code = $2
}

substr($0, 1, 1) ~ /[01xXzZ]/ {
  value = substr($0, 1, 1)
  code = substr($0, 2)
}

{
  if (code == c_pc) pc = value
  else if (code == c_vaddr) vaddr = value
  else if (code == c_instret) instret = value
  else if (code == c_csr0_w) csr0_w = value
  else if (code == c_csr0_addr) csr0_addr = value
  else if (code == c_csr0_data) csr0_data = value
  else if (code == c_csr0_mode) csr0_mode = value
  else if (code == c_csr0_ppn) csr0_ppn = value
  else if (code == c_csr1_w) csr1_w = value
  else if (code == c_csr1_addr) csr1_addr = value
  else if (code == c_csr1_data) csr1_data = value
  else if (code == c_csr1_mode) csr1_mode = value
  else if (code == c_csr1_ppn) csr1_ppn = value
  else next
  dirty = 1
}

END {
  if (!emitted) {
    sample()
    emit()
  }
}
