/* Selected-signal FST reader. Never exports the whole waveform body. */
#include "fstapi.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_SIGNALS 256
#define NAME_SIZE 32768
struct selection { char *key, *suffix; fstHandle handle; unsigned width, matches; };
static struct selection selected[MAX_SIGNALS];
static unsigned count;

static void changed(void *unused, uint64_t time, fstHandle handle,
                    const unsigned char *value) {
  (void)unused;
  printf("%" PRIu64 "\t%u\t%s\n", time, (unsigned)handle, value);
}

int main(int argc, char **argv) {
  if (argc != 3) { fprintf(stderr, "usage: fst_events file.fst selection.tsv|--list\n"); return 2; }
  int list = !strcmp(argv[2], "--list");
  if (!list) {
    FILE *f = fopen(argv[2], "r");
    if (!f) return 3;
    char line[NAME_SIZE];
    while (fgets(line, sizeof line, f)) {
      char *tab = strchr(line, '\t');
      if (!tab || count == MAX_SIGNALS || !strchr(tab, '\n')) return 4;
      *tab++ = 0; tab[strcspn(tab, "\r\n")] = 0;
      if (!*line || !*tab || strpbrk(line, " \r\n")) return 4;
      for (unsigned i = 0; i < count; ++i)
        if (!strcmp(line, selected[i].key)) return 4;
      selected[count].key = strdup(line); selected[count].suffix = strdup(tab);
      if (!selected[count].key || !selected[count].suffix) return 4;
      ++count;
    }
    fclose(f);
    if (!count) return 4;
  }
  void *ctx = fstReaderOpen(argv[1]);
  if (!ctx) return 5;
  fstReaderClrFacProcessMaskAll(ctx);
  printf("#FST\t%" PRIu64 "\t%" PRIu64 "\t%d\n",
         fstReaderGetStartTime(ctx), fstReaderGetEndTime(ctx), fstReaderGetTimescale(ctx));
  char scope[NAME_SIZE] = "", full[NAME_SIZE];
  size_t lengths[512]; unsigned depth = 0;
  struct fstHier *h;
  while ((h = fstReaderIterateHier(ctx))) {
    if (h->htyp == FST_HT_SCOPE) {
      if (depth == 512) return 6;
      lengths[depth++] = strlen(scope);
      if (strlen(scope) + h->u.scope.name_length + 2 >= sizeof scope) return 6;
      if (*scope) strcat(scope, ".");
      strcat(scope, h->u.scope.name);
    } else if (h->htyp == FST_HT_UPSCOPE) {
      if (!depth) return 6;
      scope[lengths[--depth]] = 0;
    } else if (h->htyp == FST_HT_VAR) {
      if (snprintf(full, sizeof full, "%s.%s", scope, h->u.var.name) >= (int)sizeof full) return 6;
      full[strcspn(full, " \t")] = 0;
      if (list) printf("#VAR\t%u\t%u\t%s\n", h->u.var.length, (unsigned)h->u.var.handle, full);
      for (unsigned i = 0; i < count; ++i) {
        size_t n = strlen(selected[i].suffix), m = strlen(full);
        if (m >= n && !strcmp(full + m - n, selected[i].suffix)
            && (m == n || full[m-n-1] == '.')) {
          if (++selected[i].matches != 1 || h->u.var.length > 4096) return 7;
          selected[i].handle = h->u.var.handle; selected[i].width = h->u.var.length;
          printf("#SIGNAL\t%s\t%u\t%u\t%s\n", selected[i].key,
                 selected[i].width, (unsigned)selected[i].handle, full);
          fstReaderSetFacProcessMask(ctx, selected[i].handle);
        }
      }
    }
  }
  for (unsigned i = 0; i < count; ++i) if (selected[i].matches != 1) {
    fprintf(stderr, "missing/ambiguous selected signal: %s\n", selected[i].suffix); return 8;
  }
  if (!list && !fstReaderIterBlocks(ctx, changed, NULL, NULL)) return 9;
  printf("#END\n");
  fstReaderClose(ctx);
  for (unsigned i = 0; i < count; ++i) { free(selected[i].key); free(selected[i].suffix); }
  return ferror(stdout) ? 10 : 0;
}
