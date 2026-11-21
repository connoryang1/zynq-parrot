"""Compile the actual new kernel branches with only hardware/user primitives mocked.

The host fixture exercises real fork/wait, uses simulated credentials, and never
issues a host prctl or CSR. The inline-assembly contract is checked before its
two hardware operations are replaced; this does not test an actual illegal trap.
"""
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
PATCH = HERE / "kernel-patches/0029-blackparrot-retained-control.patch"


def kernel_branches():
    added = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                      if line.startswith("+") and not line.startswith("+++"))
    helpers = added.split("static int bp_retained_probe", 1)[1].split("#else", 1)[0]
    helpers = "static int bp_retained_probe" + helpers
    read_asm = re.search(r'asm volatile\("1: csrr.*?: : "memory"\);', helpers, re.S)
    if not read_asm or read_asm.group().count("0x5c2") != 1:
        raise AssertionError("unexpected CSR read contract")
    for token in ('_ASM_EXTABLE_UACCESS_ERR_ZERO(1b, 2b, %[err], %[value])',
                  '[err] "+&r" (err)', '[value] "+&r" (value)'):
        if token not in read_asm.group():
            raise AssertionError("missing safe read/independent early-clobber outputs")
    helpers = helpers.replace(read_asm.group(), "mock_csr_read(&value, &err);")
    write_asm = 'asm volatile("csrw 0x5c2, %0\\n" : : "r" (mask) : "memory");'
    if helpers.count(write_asm) != 1 or "fence.i" in helpers:
        raise AssertionError("unexpected control submission contract")
    helpers = helpers.replace(write_asm, "mock_csr_write(mask);")
    cases = "\tcase PR_BP_RETAINED_CONTROL:" + added.split("\tcase PR_BP_RETAINED_CONTROL:", 1)[1]
    return helpers, cases


MOCK_C = r'''
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
typedef uint64_t u64;
#define __user
#define CAP_SYS_ADMIN 21
#define PR_BP_RETAINED_CONTROL 0x42505063
#define PR_BP_RETAINED_STATUS 0x42505064
struct state { unsigned mode, reads, writes, busy; };
static struct state *s;
static unsigned uid, gid, depth, copies, copy_depth;
static unsigned long envnum(const char *name, unsigned long fallback) {
 const char *v=getenv(name); return v?strtoul(v,0,0):fallback;
}
static unsigned flag(const char *name) { return envnum(name,0)!=0; }
__attribute__((constructor)) static void setup(void) {
 s=mmap(0,sizeof(*s),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
 if(s==MAP_FAILED) abort();
 uid=envnum("MOCK_UID",0); gid=uid;
}
uid_t __wrap_geteuid(void) { return uid; }
gid_t __wrap_getegid(void) { return gid; }
int __wrap_setuid(uid_t value) {
 if(flag("MOCK_DROP_FAIL")) { errno=EPERM; return -1; } uid=value; return 0;
}
int __wrap_setgid(gid_t value) {
 if(flag("MOCK_DROP_FAIL")) { errno=EPERM; return -1; } gid=value; return 0;
}
static int capable(int cap) { return cap==CAP_SYS_ADMIN && (!uid || flag("MOCK_PRIV_BYPASS")); }
static unsigned num_possible_cpus(void) { return envnum("MOCK_CPUS",1); }
static void preempt_disable(void) { if(depth++) abort(); }
static void preempt_enable(void) { if(depth!=1) abort(); --depth; }
static unsigned normalize(unsigned mask) {
 if(!envnum("MOCK_I_LINES",65)) mask&=~9U;
 if(!envnum("MOCK_D_LINES",1320)) mask&=~6U;
 if(!(mask&1)) mask&=~8U;
 if(!(mask&2)) mask&=~4U;
 return mask;
}
static void mock_csr_read(unsigned long *value,unsigned long *err) {
 if(depth!=1) abort();
 ++s->reads;
 *err=flag("MOCK_ABSENT")?EFAULT:0;
 *value=0;
 if(*err) return;
 *value=(UINT64_C(1)<<63)|(UINT64_C(3)<<56)
   |(envnum("MOCK_SET_LOG2",6)<<48)|(envnum("MOCK_D_LINES",1320)<<32)
   |(envnum("MOCK_I_LINES",65)<<16)|s->mode|envnum("MOCK_WRAP",0);
 if(s->busy || flag("MOCK_BUSY_FOREVER")) { *value|=0x300; if(s->busy) --s->busy; }
 if(flag("MOCK_NO_CAP")) *value&=~(UINT64_C(1)<<63);
 if(flag("MOCK_TRUNCATE")) *value&=UINT64_C(0xffffffff);
 if(flag("MOCK_NO_FULL64")) *value&=~(UINT64_C(1)<<56);
 if(flag("MOCK_RESERVED")) *value|=0x10;
 if(flag("MOCK_GEOMETRY_DRIFT") && s->writes) *value^=UINT64_C(1)<<16;
}
static void mock_csr_write(unsigned long mask) {
 if(depth!=1) abort();
 ++s->writes;
 if(!flag("MOCK_IGNORE_WRITE") || !mask) s->mode=normalize(mask);
 if(flag("MOCK_BAD_CLEAR") && !mask && s->writes>1) s->mode=1;
 s->busy=envnum("MOCK_BUSY_READS",3);
}
static int copy_to_user(u64 *dst,const u64 *src,size_t n) {
 ++copies; copy_depth=depth;
 if(depth || n!=8) abort();
 if((uintptr_t)dst<4096) return 1;
 memcpy(dst,src,n); return 0;
}
/* ACTUAL_HELPERS */
static long kernel_call(int option,unsigned long arg2,unsigned long arg3,
                        unsigned long arg4,unsigned long arg5) {
 long error=0;
 switch(option) {
 /* ACTUAL_CASES */
 default: error=-EINVAL;
 }
 return error;
}
int __wrap_prctl(int option,...) {
 va_list ap; va_start(ap,option);
 unsigned long a2=va_arg(ap,unsigned long),a3=va_arg(ap,unsigned long);
 unsigned long a4=va_arg(ap,unsigned long),a5=va_arg(ap,unsigned long);
 va_end(ap);
 long result=kernel_call(option,a2,a3,a4,a5);
 if(uid && flag("MOCK_DENIED_MUTATION") && option==PR_BP_RETAINED_CONTROL && result==-EPERM)
   s->mode=0;
 if(flag("MOCK_DIRTY_ERROR") && result<0 && option==PR_BP_RETAINED_STATUS && a2>=4096)
   *(u64 *)a2=0;
 const char *path=getenv("MOCK_LOG");
 if(path) {
   int fd=open(path,O_WRONLY|O_CREAT|O_APPEND,0600);
   if(fd<0) abort();
   dprintf(fd,"%ld %u %x %lu %ld %u %u %u %u\n",(long)getpid(),uid,option,a2,result,
           s->mode,s->reads,s->writes,depth);
   close(fd);
 }
 if(result<0) { errno=-result; return -1; }
 return result;
}
#ifdef CONTRACT_MAIN
int main(int argc,char **argv) {
 if(argc!=7) return 2;
 unsigned long a2=strtoul(argv[2],0,0),a3=strtoul(argv[3],0,0);
 unsigned long a4=strtoul(argv[4],0,0),a5=strtoul(argv[5],0,0);
 u64 out=UINT64_C(0x0123456789abcdef);
 if(!strcmp(argv[6],"ptr")) a2=(unsigned long)&out;
 long rc=kernel_call(strtoul(argv[1],0,0),a2,a3,a4,a5);
 printf("{\"rc\":%ld,\"out\":%llu,\"mode\":%u,\"reads\":%u,\"writes\":%u,"
        "\"depth\":%u,\"copies\":%u,\"copy_depth\":%u}\n",rc,(unsigned long long)out,
        s->mode,s->reads,s->writes,depth,copies,copy_depth);
 return 0;
}
#endif
'''


def compile_fixture(directory, probe=False):
    directory = Path(directory)
    helpers, cases = kernel_branches()
    source = directory / ("probe-mock.c" if probe else "kernel-mock.c")
    source.write_text(MOCK_C.replace("/* ACTUAL_HELPERS */", helpers)
                      .replace("/* ACTUAL_CASES */", cases))
    binary = directory / ("probe" if probe else "kernel-contract")
    command = [os.environ.get("BP_HOST_CC", "cc"), "-O2", "-std=c11", "-Wall", "-Wextra",
               "-Werror", "-o", str(binary), str(source)]
    if probe:
        command += ["-DBP_RETAINED_PROBE_HOST_VERIFY=1", str(HERE / "retained_store_probe.c")]
        command += ["-Wl,--wrap=" + name for name in
                    ("prctl", "geteuid", "getegid", "setuid", "setgid")]
    else:
        command += ["-DCONTRACT_MAIN=1"]
    result = subprocess.run(command, text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return binary
