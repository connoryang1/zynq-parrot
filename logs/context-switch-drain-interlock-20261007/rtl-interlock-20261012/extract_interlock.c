#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fstapi.h"

enum { CLK, RESET, COMMIT, SETTLE, EMPTY, SUPPRESS, HOLD, PTW, HAZARD, COUNT };
struct signal { const char *suffix; fstHandle handle; char value[96]; };
static struct signal signals[COUNT] = {
  [CLK]      = {.suffix = ".core_minimal.be.clk_i"},
  [RESET]    = {.suffix = ".core_minimal.be.reset_i"},
  [COMMIT]   = {.suffix = ".be.commit_pkt.ctxtsw"},
  [SETTLE]   = {.suffix = ".be.scheduler.ctxtsw_target_settle_r"},
  [EMPTY]    = {.suffix = ".be.scheduler.issue_queue_empty_lo"},
  [SUPPRESS] = {.suffix = ".be.scheduler.suppress_iss_i"},
  [HOLD]     = {.suffix = ".be.scheduler.ctxtsw_issue_hold_r"},
  [PTW]      = {.suffix = ".be.scheduler.ptw_busy_lo"},
  [HAZARD]   = {.suffix = ".be.scheduler.hazard_v_i"},
};

static uint64_t value(int i) {
  return signals[i].value[0] ? strtoull(signals[i].value, 0, 2) : 0;
}
static int ends_with(const char *s, const char *suffix) {
  size_t n = strlen(s), m = strlen(suffix);
  return n >= m && !strcmp(s + n - m, suffix);
}

static uint64_t settle_edges, exposed_edges, commit_edges;
static uint64_t settle_pulses, commit_pulses;
static int reset_seen, reset_released;
static void change(void *unused, uint64_t time, fstHandle handle,
                   const unsigned char *raw) {
  (void)unused; (void)time;
  int old_clk = value(CLK);
  int old_reset = value(RESET);
  int old_commit = value(COMMIT);
  int old_settle = value(SETTLE);
  for (int i = 0; i < COUNT; ++i)
    if (signals[i].handle == handle) {
      snprintf(signals[i].value, sizeof signals[i].value, "%s", raw);
      break;
    }
  if (handle == signals[RESET].handle) {
    if (value(RESET)) reset_seen = 1;
    if (reset_seen && old_reset && !value(RESET)) reset_released = 1;
  }
  if (reset_released && handle == signals[COMMIT].handle
      && !old_commit && value(COMMIT))
    ++commit_pulses;
  if (reset_released && handle == signals[SETTLE].handle
      && !old_settle && value(SETTLE))
    ++settle_pulses;
  int clk = value(CLK);
  if (!old_clk && clk && !value(RESET)) {
    commit_edges += !!value(COMMIT);
    settle_edges += !!value(SETTLE);
    exposed_edges += value(SETTLE) && !value(EMPTY) && !value(SUPPRESS)
                     && !value(HOLD) && !value(PTW) && !value(HAZARD);
  }
}

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  void *reader = fstReaderOpen(argv[1]);
  if (!reader) return 1;
  fstReaderClrFacProcessMaskAll(reader);
  char scopes[256][256], fullname[8192];
  int depth = 0;
  struct fstHier *hier;
  while ((hier = fstReaderIterateHier(reader))) {
    if (hier->htyp == FST_HT_SCOPE)
      snprintf(scopes[depth++], sizeof scopes[0], "%s", hier->u.scope.name);
    else if (hier->htyp == FST_HT_UPSCOPE) {
      if (depth) --depth;
    } else if (hier->htyp == FST_HT_VAR) {
      fullname[0] = 0;
      for (int i = 0; i < depth; ++i) {
        if (i) strcat(fullname, ".");
        strcat(fullname, scopes[i]);
      }
      if (depth) strcat(fullname, ".");
      strcat(fullname, hier->u.var.name);
      char *space = strchr(fullname, ' ');
      if (space) *space = 0;
      for (int i = 0; i < COUNT; ++i)
        if (!signals[i].handle && ends_with(fullname, signals[i].suffix)) {
          signals[i].handle = hier->u.var.handle;
          fstReaderSetFacProcessMask(reader, signals[i].handle);
          break;
        }
    }
  }
  for (int i = 0; i < COUNT; ++i)
    if (!signals[i].handle) {
      fprintf(stderr, "missing %s\n", signals[i].suffix);
      return 3;
    }
  int ok = fstReaderIterBlocks(reader, change, 0, 0);
  fstReaderClose(reader);
  printf("commit_pulses=%" PRIu64 " settle_pulses=%" PRIu64
         " commit_edges=%" PRIu64 " settle_edges=%" PRIu64
         " exposed_edges=%" PRIu64 "\n", commit_pulses, settle_pulses,
         commit_edges, settle_edges, exposed_edges);
  return ok ? 0 : 4;
}
