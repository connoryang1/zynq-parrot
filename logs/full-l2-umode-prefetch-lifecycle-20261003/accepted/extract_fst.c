#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fstapi.h"

struct sel { fstHandle h; char *name; } sels[64];
static size_t nsels;

static int member(const char *s, const char *const *set) {
  for (size_t i = 0; set[i]; i++) if (!strcmp(s, set[i])) return 1;
  return 0;
}
static const char *dcache[] = {"prefetch_buffer_v_r", "prefetch_buffer_hit_tv",
  "prefetch_buffer_write", "prefetch_req", NULL};
static const char *uce[] = {"prefetch_valid_r", "prefetch_sent_r", "prefetch_drop", NULL};
static const char *pipe_names[] = {"prefetch_mmu_r", "dtlb_v_lo", "dtlb_load_miss_lo",
  "prefetch_ptag_allowed", "eaddr", NULL};

static const char *name_for(fstHandle h) {
  for (size_t i = 0; i < nsels; i++) if (sels[i].h == h) return sels[i].name;
  return NULL;
}
static int selected_name(const char *name) {
  for (size_t i = 0; i < nsels; i++) if (!strcmp(sels[i].name, name)) return 1;
  return 0;
}
static void cb(void *outp, uint64_t t, fstHandle h, const unsigned char *v) {
  const char *name = name_for(h);
  if (name) fprintf((FILE *)outp, "%" PRIu64 " %s %s\n", t, name, v);
}

int main(int argc, char **argv) {
  if (argc != 3) { fprintf(stderr, "usage: %s input.fst events.txt\n", argv[0]); return 2; }
  void *ctx = fstReaderOpen(argv[1]);
  if (!ctx) { perror("fstReaderOpen"); return 1; }
  struct fstHier *it;
  while ((it = fstReaderIterateHier(ctx))) {
    if (it->htyp != FST_HT_VAR) continue;
    const char *ref = it->u.var.name;
    char base[256];
    size_t n = strcspn(ref, " [");
    if (n >= sizeof(base)) continue;
    memcpy(base, ref, n);
    base[n] = 0;
    int take = member(base, dcache) || member(base, pipe_names)
      || (member(base, uce)
          && (strcmp(base, "prefetch_drop") == 0 || it->u.var.length == 10));
    if (!take) continue;
    if (selected_name(base)) continue;
    if (name_for(it->u.var.handle)) continue;
    if (nsels == sizeof(sels)/sizeof(sels[0])) return 3;
    sels[nsels].h = it->u.var.handle;
    sels[nsels].name = strdup(base);
    fstReaderSetFacProcessMask(ctx, it->u.var.handle);
    fprintf(stderr, "selected h=%u len=%u %s\n", it->u.var.handle,
            it->u.var.length, base);
    nsels++;
  }
  if (nsels != 12) { fprintf(stderr, "expected 12 signals, found %zu\n", nsels); return 4; }
  FILE *out = fopen(argv[2], "w");
  if (!out) { perror("fopen"); return 5; }
  int rc = !fstReaderIterBlocks(ctx, cb, out, NULL);
  fclose(out);
  fstReaderClose(ctx);
  return rc;
}
