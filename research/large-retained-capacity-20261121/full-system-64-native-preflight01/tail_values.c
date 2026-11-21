/* Read selected closed-FST values directly; no full memory-array VCD export.
 * This diagnostic reports sampled signal values, not retired instructions.
 */
#include "fstapi.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
int main(int argc, char **argv) {
  if (argc < 3) return 2;
  void *ctx = fstReaderOpen(argv[1]);
  if (!ctx) return 3;
  fstHandle handles[32] = {0};
  if (argc-2 > 32) return 4;
  char scope[16384] = "", full[18000];
  size_t lengths[256]; unsigned depth = 0;
  struct fstHier *h;
  while ((h = fstReaderIterateHier(ctx))) {
    if (h->htyp == FST_HT_SCOPE) {
      if (depth == 256) return 5;
      lengths[depth++] = strlen(scope);
      if (*scope) strcat(scope, ".");
      if (strlen(scope)+h->u.scope.name_length+1 >= sizeof scope) return 6;
      strcat(scope, h->u.scope.name);
    } else if (h->htyp == FST_HT_UPSCOPE) {
      if (!depth) return 7;
      scope[lengths[--depth]] = 0;
    } else if (h->htyp == FST_HT_VAR) {
      snprintf(full,sizeof full,"%s.%s",scope,h->u.var.name);
      full[strcspn(full," \t")] = 0; // FST vector names include the range.
      for (int j=2;j<argc;++j) {
        size_t n=strlen(argv[j]), m=strlen(full);
        if (m >= n && !strcmp(full+m-n,argv[j]) && (m==n || full[m-n-1]=='.')) {
          if (handles[j-2] || h->u.var.length>1024) return 8;
          handles[j-2]=h->u.var.handle;
          fprintf(stderr,"%s\t%s\t%u\n",argv[j],full,h->u.var.handle);
        }
      }
    }
  }
  uint64_t end=fstReaderGetEndTime(ctx);
  for (int j=2;j<argc;++j) if (!handles[j-2]) return 9;
  fprintf(stderr,"end=%" PRIu64 " timescale_exp=%d\n",end,fstReaderGetTimescale(ctx));
  const uint64_t offsets[]={100000000,10000000,1000000,100000,0};
  for (unsigned k=0;k<sizeof offsets/sizeof offsets[0];++k) {
    if (end<offsets[k]) continue;
    for (int j=2;j<argc;++j) {
      char value[2048];
      if (!fstReaderGetValueFromHandleAtTime(ctx,end-offsets[k],handles[j-2],value)) return 10;
      printf("%" PRIu64 "\t%s\t%s\n",end-offsets[k],argv[j],value);
    }
  }
  fstReaderClose(ctx); return 0;
}
