
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
static unsigned calls, mode;
static pid_t owner;
static int log_fd;
static void event(const char *name, long value)
{
    dprintf(log_fd, "%s pid=%ld value=%ld\n", name, (long)getpid(), value);
}
__attribute__((constructor)) static void initialize(void)
{
    owner = getpid();
    log_fd = open(getenv("BP_RESOURCE_MOCK_LOG"), O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (log_fd < 0) _exit(90);
}
pid_t __real_fork(void);
pid_t __wrap_fork(void)
{
    pid_t child = __real_fork();
    if (child > 0) event("fork", child);
    return child;
}
pid_t __real_waitpid(pid_t, int *, int);
pid_t __wrap_waitpid(pid_t child, int *status, int options)
{
    pid_t result = __real_waitpid(child, status, options);
    event("wait", result);
    return result;
}
void __real_free(void *);
void __wrap_free(void *memory)
{
    if (memory) event("free", 0);
    __real_free(memory);
}
int __real_munmap(void *, size_t);
int __wrap_munmap(void *memory, size_t size)
{
    event("munmap", 0);
    return __real_munmap(memory, size);
}
int deterministic_getrusage(int who, struct rusage *usage)
{
    unsigned cell = calls / 4, position = calls++ % 4;
    int child = who == RUSAGE_CHILDREN, end = position >= 2;
    const char *fault = getenv("BP_RESOURCE_MOCK_FAULT");
    const char *failure = getenv("BP_RESOURCE_MOCK_FAILURE_CALL");
    const char *delay = getenv("BP_RESOURCE_MOCK_DELAY");
    long base = (child ? 9000 + cell * 1000 : 1000 + cell * 100);
    if (getpid() != owner || child != (int)(position & 1) ||
        (who != RUSAGE_SELF && who != RUSAGE_CHILDREN)) _exit(91);
    event("usage", calls);
    if (failure && calls == strtoul(failure, NULL, 10)) { errno = EIO; return -1; }
    if (delay) {
        struct timespec pause = { .tv_nsec = 2000000 };
        while (nanosleep(&pause, &pause) && errno == EINTR) { }
    }
    memset(usage, 0, sizeof(*usage));
    usage->ru_minflt = base + (end ? (child ? 13 : 3) : 0);
    usage->ru_majflt = base + 50 + (end ? (child ? 17 : 5) : 0);
    usage->ru_nvcsw = base + 100 + (end ? (child ? 19 : 7) : 0);
    usage->ru_nivcsw = base + 150 + (end ? (child ? 23 : 11) : 0);
    usage->ru_utime.tv_sec = (child ? 100 + cell * 9 : 10 + cell * 3) + end;
    usage->ru_utime.tv_usec = end ? 100000 : (child ? 800000 : 900000);
    usage->ru_stime.tv_sec = (child ? 200 + cell * 9 : 20 + cell * 3) + end;
    usage->ru_stime.tv_usec = end ? (child ? 40 : 20) : (child ? 999980 : 999990);
    if (fault && end) {
        if (!strcmp(fault, "negative-counter")) usage->ru_minflt = base - 1;
        if (!strcmp(fault, "negative-time")) {
            --usage->ru_utime.tv_sec;
            usage->ru_utime.tv_usec = 0;
        }
        if (!strcmp(fault, "invalid-usec")) usage->ru_utime.tv_usec = 1000000;
        if (!strcmp(fault, "time-overflow")) usage->ru_utime.tv_sec = LONG_MAX;
    }
    if (fault && !strcmp(fault, "negative-base")) usage->ru_minflt = -1;
    if (fault && !strcmp(fault, "sum-overflow")) {
        usage->ru_utime.tv_sec = end ? INT64_C(10000000000000) : 0;
        usage->ru_utime.tv_usec = 0;
    }
    return 0;
}
/* The optional retention mock records the same stream as the observers.
 * Resource-only binaries link without these functions being called.
 */
int bp_resume_host_retention_prctl(int option, unsigned long arg2,
                                  unsigned long arg3, unsigned long arg4, unsigned long arg5)
{
    if (getpid() != owner || arg3 || arg4 || arg5) _exit(92);
    if (option == 0x42505061) {
        event("control", arg2);
        mode = arg2;
        return 0;
    }
    if (option != 0x42505062 || !arg2) _exit(93);
    event("status", mode);
    *(uint64_t *)arg2 = (UINT64_C(1) << 63) | mode | (mode ? 4 : 0);
    return 0;
}
void bp_resume_host_retention_hint(unsigned enabled) { (void)enabled; }
void bp_resume_host_retention_task_mode(unsigned enabled) { event("task_mode", enabled); }

#include <stdarg.h>
struct hw { unsigned mode, busy, writes, source_count, injected, replay_reads, data_count, data_injected; };
static struct hw *hw;
static const char *fault;
static int isfault(const char *name) { return fault && !strcmp(fault,name); }
int __real_getrusage(int,struct rusage *);
int __wrap_getrusage(int who,struct rusage *usage) {
    if(getenv("R29_REAL_USAGE")) {
        if(getpid()!=owner) _exit(94);
        event("actual_usage",who);
        return __real_getrusage(who,usage);
    }
    return deterministic_getrusage(who,usage);
}
__attribute__((constructor)) static void hw_init(void) {
    hw=mmap(0,sizeof(*hw),PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
    if(hw==MAP_FAILED) _exit(95);
    fault=getenv("R29_FAULT");
    if(isfault("initial-active")) hw->mode=9;
}
__attribute__((destructor)) static void hw_final(void) {
    if(getpid()==owner) event("final_mode",hw->mode);
}
long bp_retained29_host_replay_status(void) {
    if(getpid()!=owner) _exit(93);
    ++hw->replay_reads;
    uint64_t raw=UINT64_C(3)<<58;
    if(isfault("replay-activity") && hw->writes>=2 && !hw->data_injected) {
        hw->data_count=1;hw->data_injected=1;
    }
    raw|=(uint64_t)hw->data_count<<10;
    if(isfault("replay-saturated")) raw|=UINT64_C(65535)<<10;
    if(hw->replay_reads<3 || isfault("replay-busy")) raw|=(UINT64_C(1)<<63)|(UINT64_C(2)<<60);
    event("replay",(long)raw);
    return (long)raw;
}
void *__real_calloc(size_t,size_t);
void *__wrap_calloc(size_t n,size_t size) {
    event("allocation",n*size);
    if((isfault("child-allocation") && getpid()!=owner) ||
       (isfault("parent-allocation") && getpid()==owner)) { errno=ENOMEM; return 0; }
    return __real_calloc(n,size);
}
int __wrap_prctl(int option,...) {
    va_list ap;va_start(ap,option);
    unsigned long a2=va_arg(ap,unsigned long),a3=va_arg(ap,unsigned long);
    unsigned long a4=va_arg(ap,unsigned long),a5=va_arg(ap,unsigned long);va_end(ap);
    if(a3||a4||a5) _exit(96);
    if(option==0x4250505a) {
        event("task_mode",a2);
        if(a2) _exit(97);
        if(isfault("source-off") && hw->mode && getpid()==owner) { errno=EIO;return -1; }
        return 0;
    }
    if(option==0x4250505e) {
        if(isfault("prefix-activity") && hw->writes>=2 && !hw->injected) { hw->source_count=1;hw->injected=1; }
        uint64_t raw=1|(32UL<<4)|((uint64_t)hw->source_count<<38);
        if(isfault("prefix-busy")) raw|=2;
        if(isfault("prefix-saturated")) raw|=UINT64_C(255)<<38;
        *(uint64_t *)a2=raw;event("prefix",hw->source_count);return 0;
    }
    if(option==0x42505063) {
        event("r29_control",a2);
        if(getpid()!=owner || a2>15) _exit(98);
        if(isfault("control-failure") && a2) { errno=EIO; return -1; }
        ++hw->writes;hw->mode=a2;hw->busy=3;
        if(isfault("wrong-readback") && a2) hw->mode=0;
        if(isfault("bad-reset") && !a2 && hw->writes>1) hw->mode=1;
        return 0;
    }
    if(option==0x42505064) {
        event("r29_status",hw->mode);
        if(getpid()!=owner) _exit(99);
        if(isfault("absent")) { errno=ENODEV;return -1; }
        uint64_t raw=(UINT64_C(1)<<63)|(UINT64_C(3)<<56)|(UINT64_C(6)<<48)
          |(UINT64_C(1320)<<32)|(UINT64_C(65)<<16)|hw->mode;
        if(hw->busy || (isfault("busy") && hw->writes)) { raw|=0x300;if(hw->busy)--hw->busy; }
        if(isfault("truncated")) raw&=0xffffffff;
        if(isfault("no-i")) raw&=~(UINT64_C(65535)<<16);
        if(isfault("no-d")) raw&=~(UINT64_C(65535)<<32);
        if(isfault("reserved")) raw|=16;
        if(isfault("geometry-drift") && hw->writes) raw^=UINT64_C(1)<<16;
        *(uint64_t *)a2=raw;return 0;
    }
    event("FORBIDDEN_PRCTL",option);errno=EINVAL;return -1;
}
static void report_guard(void) {
    event("report",hw->mode);
    if(hw->mode) _exit(100);
}
int __wrap_printf(const char *format,...) {
    report_guard();va_list ap;va_start(ap,format);int r=vprintf(format,ap);va_end(ap);return r;
}
int __real_puts(const char *);
int __wrap_puts(const char *text) { report_guard();return __real_puts(text); }
