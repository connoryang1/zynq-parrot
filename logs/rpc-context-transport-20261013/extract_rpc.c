#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fstapi.h"
enum { CLK, DV, DPC, COUNT };
struct sig { const char *s; fstHandle h; char v[96]; };
static struct sig a[COUNT] = {
  [CLK] = {.s = ".core_minimal.be.clk_i"},
  [DV] = {.s = ".be.scheduler.dispatch_pkt_cast_o.v"},
  [DPC] = {.s = ".be.scheduler.dispatch_pkt_cast_o.pc"},
};
static uint64_t t; static int have_time;
static int ends(const char *s,const char *x){size_t n=strlen(s),m=strlen(x);return n>=m&&!strcmp(s+n-m,x);}
static uint64_t val(int i){return a[i].v[0]?strtoull(a[i].v,0,2):0;}
static void flush(void){
  uint64_t pc=val(DPC);
  if(have_time && val(DV) && (pc<UINT64_C(0x30000) || (pc>=UINT64_C(0x80002000) && pc<UINT64_C(0x80002400))))
    printf("%"PRIu64"\t0x%"PRIx64"\n",t,pc);
}
static void change(void *unused,uint64_t tt,fstHandle h,const unsigned char *v){
  (void)unused; if(have_time&&tt!=t)flush();t=tt;have_time=1;
  for(int i=0;i<COUNT;i++)if(a[i].h==h){snprintf(a[i].v,sizeof a[i].v,"%s",v);break;}
}
int main(int c,char **v){if(c!=2)return 2;void*x=fstReaderOpen(v[1]);if(!x)return 1;fstReaderClrFacProcessMaskAll(x);
  char scopes[256][256],f[8192];int d=0;struct fstHier*i;
  while((i=fstReaderIterateHier(x))){if(i->htyp==FST_HT_SCOPE)snprintf(scopes[d++],256,"%s",i->u.scope.name);else if(i->htyp==FST_HT_UPSCOPE){if(d)--d;}else if(i->htyp==FST_HT_VAR){f[0]=0;for(int j=0;j<d;j++){if(j)strcat(f,".");strcat(f,scopes[j]);}if(d)strcat(f,".");strcat(f,i->u.var.name);char*s=strchr(f,' ');if(s)*s=0;for(int j=0;j<COUNT;j++)if(!a[j].h&&ends(f,a[j].s)){a[j].h=i->u.var.handle;fstReaderSetFacProcessMask(x,a[j].h);break;}}}
  for(int j=0;j<COUNT;j++)if(!a[j].h){fprintf(stderr,"missing %s\n",a[j].s);return 3;}
  puts("time\tpc");int ok=fstReaderIterBlocks(x,change,0,0);flush();fstReaderClose(x);return ok?0:4;}
