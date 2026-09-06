// Export selected FST signal suffixes as VCD without decoding unrelated values.
// This retains original hierarchy and timestamps; aliases share one FST handle.
#include "fstapi.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <cstdint>

static uint64_t last_time = UINT64_MAX;
static void change(void *, uint64_t time, fstHandle handle, const unsigned char *value) {
  if (time != last_time) {
    printf("#%llu\n", (unsigned long long) time);
    last_time = time;
  }
  printf("b%s h%u\n", value, handle);
}
int main(int argc, char **argv) {
  if (argc < 3) {
    fprintf(stderr, "usage: %s trace.fst signal-suffix [...]\n", argv[0]);
    return 2;
  }
  void *ctx = fstReaderOpen(argv[1]);
  if (!ctx) { fprintf(stderr, "cannot open FST\n"); return 1; }
  int scale = fstReaderGetTimescale(ctx);
  const char *units[] = {"s", "ms", "us", "ns", "ps", "fs", "as"};
  int unit = 0, multiplier = 1;
  while (scale < 0 && unit < 6) { scale += 3; ++unit; }
  while (scale-- > 0) multiplier *= 10;
  printf("$timescale %d%s $end\n", multiplier, units[unit]);
  fstReaderClrFacProcessMaskAll(ctx);
  std::vector<std::string> scopes;
  std::vector<bool> found(argc, false);
  fstHier *hier;
  while ((hier = fstReaderIterateHier(ctx))) {
    if (hier->htyp == FST_HT_SCOPE) {
      scopes.emplace_back(hier->u.scope.name);
      printf("$scope module %s $end\n", hier->u.scope.name);
    } else if (hier->htyp == FST_HT_UPSCOPE) {
      scopes.pop_back();
      printf("$upscope $end\n");
    } else if (hier->htyp == FST_HT_VAR) {
      std::string name;
      for (const auto &scope : scopes) name += scope + ".";
      name += hier->u.var.name;
      // VCD declarations may contain a vector range after the signal name.
      auto space = name.find(' ');
      if (space != std::string::npos) name.resize(space);
      bool selected = false;
      for (int i = 2; i < argc; ++i) {
        std::string suffix = argv[i];
        if (name == suffix || (name.size() > suffix.size()
            && name.compare(name.size() - suffix.size(), suffix.size(), suffix) == 0
            && name[name.size() - suffix.size() - 1] == '.')) {
          selected = true; found[i] = true;
        }
      }
      if (selected) {
        fstReaderSetFacProcessMask(ctx, hier->u.var.handle);
        printf("$var wire %u h%u %s $end\n", hier->u.var.length,
               hier->u.var.handle, hier->u.var.name);
      }
    }
  }
  for (int i = 2; i < argc; ++i) if (!found[i]) {
    fprintf(stderr, "missing signal suffix: %s\n", argv[i]);
    fstReaderClose(ctx); return 1;
  }
  printf("$enddefinitions $end\n");
  int ok = fstReaderIterBlocks(ctx, change, nullptr, nullptr);
  fstReaderClose(ctx);
  return ok ? 0 : 1;
}
