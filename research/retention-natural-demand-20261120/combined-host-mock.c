
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/futex.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
struct controller { _Atomic unsigned pending, armed, retained_mode; };
static struct controller *controller;
static pid_t owner;
static unsigned mode;
static int log_fd;
static void event(const char *name, long value)
{
    dprintf(log_fd, "%s pid=%ld mode=%u pending=%u value=%ld\n", name,
            (long)getpid(), mode, atomic_load(&controller->pending), value);
}
static void outside(void)
{
    if (getpid() == owner && (mode || atomic_load(&controller->pending) || atomic_load(&controller->retained_mode))) _exit(93);
    if (getpid() == owner) event("retention_idle", atomic_load(&controller->retained_mode));
}
void *__real_mmap(void *, size_t, int, int, int, off_t);
__attribute__((constructor)) static void initialize(void)
{
    owner = getpid();
    controller = __real_mmap(NULL, sizeof(*controller), PROT_READ | PROT_WRITE,
                             MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (controller == MAP_FAILED) _exit(90);
    log_fd = open(getenv("BP_SCOPE_LOG"), O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (log_fd < 0) _exit(91);
    mode = 14; /* A new program must explicitly clear possible inherited state. */
    atomic_store(&controller->pending, 4);
}
int __wrap_prctl(int option, ...)
{
    va_list ap;
    va_start(ap, option);
    unsigned long a = va_arg(ap, unsigned long), b = va_arg(ap, unsigned long);
    unsigned long c = va_arg(ap, unsigned long), d = va_arg(ap, unsigned long);
    va_end(ap);
    if (b || c || d) _exit(92);
    if (option == 0x4250505a) {
        if (a != 0 && a != 14) _exit(92);
        if (getenv("BP_SCOPE_RESET_FAIL") && !a) { errno = EIO; return -1; }
        mode = a;
        if (mode) atomic_store(&controller->armed, 1);
        event("mode", a);
        return 0;
    }
    if (option == 0x4250505f) {
        event("hint", a);
        if (a) atomic_store(&controller->pending, 4);
        return 0;
    }
    if (option != 0x4250505e || !a) _exit(92);
    if (getenv("BP_SCOPE_STATUS_FAIL") && atomic_load(&controller->armed)) {
        errno = EIO; return -1;
    }
    unsigned pending = atomic_load(&controller->pending);
    uint64_t status = (32UL << 4) | 1;
    if (pending) {
        static const uint64_t bits[] = {0, UINT64_C(1)<<54, 8, 4, 2};
        status |= bits[pending > 4 ? 4 : pending];
        if (!(getenv("BP_SCOPE_NEVER_DRAIN") && atomic_load(&controller->armed))) {
            if (getenv("BP_SCOPE_POLL_DELAY")) {
                struct timespec pause = {.tv_nsec = 2000000};
                nanosleep(&pause, NULL);
            }
            atomic_fetch_sub(&controller->pending, 1);
        }
    }
    *(unsigned long *)a = status;
    event("poll", status);
    return 0;
}
long __real_syscall(long, ...);
long __wrap_syscall(long number, ...)
{
    if (number != SYS_futex) _exit(94);
    va_list ap;
    va_start(ap, number);
    uint32_t *word = va_arg(ap, uint32_t *);
    int operation = va_arg(ap, int);
    unsigned value = va_arg(ap, unsigned);
    void *timeout = va_arg(ap, void *), *second = va_arg(ap, void *);
    int third = va_arg(ap, int);
    va_end(ap);
    if (operation == FUTEX_WAKE && mode) atomic_store(&controller->pending, 4);
    return __real_syscall(number, word, operation, value, timeout, second, third);
}
pid_t __real_fork(void);
pid_t __wrap_fork(void)
{
    pid_t child = __real_fork();
    if (!child) mode = 0; /* Linux clone clears this per-task field. */
    event("fork", child);
    return child;
}
void *__wrap_mmap(void *p, size_t n, int prot, int flags, int fd, off_t offset)
{
    outside(); event("setup_mmap", 0);
    return __real_mmap(p, n, prot, flags, fd, offset);
}
int __real_pipe(int [2]);
int __wrap_pipe(int fds[2])
{
    outside(); event("setup_pipe", 0);
    return __real_pipe(fds);
}
pid_t __real_waitpid(pid_t, int *, int);
pid_t __wrap_waitpid(pid_t child, int *status, int options)
{
    pid_t result = __real_waitpid(child, status, options);
    event("reap", result); return result;
}
void __real_free(void *);
void __wrap_free(void *p)
{
    if (p) event("free", 0);
    __real_free(p);
}
int __real_munmap(void *, size_t);
int __wrap_munmap(void *p, size_t n)
{
    event("unmap", 0); return __real_munmap(p, n);
}
int __real_getrusage(int, struct rusage *);
int __wrap_getrusage(int who, struct rusage *usage)
{
    outside(); event("usage", who);
    return __real_getrusage(who, usage);
}
int __real_clock_gettime(clockid_t, struct timespec *);
int __wrap_clock_gettime(clockid_t id, struct timespec *now)
{
    event("clock", id); return __real_clock_gettime(id, now);
}
int __wrap_printf(const char *format, ...)
{
    outside();
    long kind = strstr(format, "HOST_VERIFY_WHOLE") ? 2 :
                strstr(format, "HOST_VERIFY_RESULT") ? 1 :
                strstr(format, "HOST_VERIFY_RESOURCE") ? 3 : 0;
    event("print", kind);
    va_list ap; va_start(ap, format);
    int result = vfprintf(stdout, format, ap);
    va_end(ap); return result;
}
int __real_puts(const char *);
int __wrap_puts(const char *s)
{
    outside(); event("puts", strstr(s, "HOST_VERIFY_PASS") != NULL);
    return __real_puts(s);
}
int __real_fflush(FILE *);
int __wrap_fflush(FILE *stream)
{
    if (stream == stdout) outside();
    return __real_fflush(stream);
}

int bp_resume_host_retention_prctl(int option, unsigned long a,
                                  unsigned long b, unsigned long c, unsigned long d)
{
    if (getpid() != owner || b || c || d) _exit(95);
    if (option == 0x42505061) {
        if (a > 2) _exit(96);
        if (a && getenv("BP_COMBINED_SET_FAIL")) { errno = EIO; return -1; }
        atomic_store(&controller->retained_mode, a);
        atomic_store(&controller->armed, 1);
        /* Synthetic reported pending states exercise ending scope cleanup;
         * this is not a claim about hardware traffic from a policy reset. */
        if (!a) atomic_store(&controller->pending, 4);
        event("retention_control", a);
        return 0;
    }
    if (option != 0x42505062 || !a) _exit(97);
    if (getenv("BP_COMBINED_OLD")) { errno = ENODEV; return -1; }
    unsigned retained = atomic_load(&controller->retained_mode);
    event("retention_status", retained);
    *(uint64_t *)a = (UINT64_C(1)<<63) | retained | (retained ? 4 : 0);
    return 0;
}
