"""Verify explicit policy cleanup with real host fork, pipe and futex execution.

The shared controller and task modes are mocks; host nanoseconds are never
FPGA performance evidence. Error injection tests bounded failure without PASS.
"""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
MOCK = r'''
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
struct controller { _Atomic unsigned pending, armed; };
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
    if (getpid() == owner && (mode || atomic_load(&controller->pending))) _exit(93);
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
'''


class CompletePolicyScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='complete-policy-scope-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.mock = cls.root / 'scope_mock.c'
        cls.mock.write_text(MOCK)
        cls.cc = os.environ.get('BP_HOST_CC', 'cc')
        cls.base = [cls.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-DBP_RESUME_HOST_VERIFY=1',
                    '-DBP_RESUME_RESOURCE_STATS=1', '-DBP_RESUME_COMPLETE_POLICY_SCOPE=1']
        cls.binary = cls.build('plain')
        cls.zlib = cls.build('zlib', zlib=True)

    @classmethod
    def build(cls, name, zlib=False):
        binary = cls.root / name
        command = cls.base + (['-DBP_RESUME_ZLIB=1'] if zlib else [])
        command += [str(HERE / 'scheduler_pipe_hint_benchmark.c'), str(cls.mock), '-o', str(binary)]
        command += ['-Wl,--wrap=' + name for name in ('prctl', 'syscall', 'fork', 'mmap', 'pipe',
                    'waitpid', 'free', 'munmap', 'getrusage', 'clock_gettime', 'printf', 'puts', 'fflush')]
        if zlib:
            command += ['-lz']
        subprocess.run(command, check=True, capture_output=True, timeout=30)
        return binary

    def run_benchmark(self, policy='futex-early', sync='futex', workload='lookup', flags=None):
        log = self.root / ('events-' + str(len(list(self.root.glob('events-*')))))
        env = os.environ.copy()
        env['BP_SCOPE_LOG'] = str(log)
        env.update(flags or {})
        selected = min(os.sched_getaffinity(0))
        run = subprocess.run([str(self.zlib if workload == 'deflate' else self.binary), '3', '2',
                              policy, '2', sync, 'plain', '32', workload],
                             env=env, text=True, capture_output=True, timeout=10,
                             preexec_fn=lambda: os.sched_setaffinity(0, {selected}))
        events = [dict(name=n, pid=int(p), mode=int(m), pending=int(q), value=int(v))
                  for n,p,m,q,v in re.findall(r'^(\w+) pid=(\d+) mode=(\d+) pending=(\d+) value=(-?\d+)$',
                                             log.read_text(), re.MULTILINE)]
        return run, events

    def test_real_forks_reset_and_drain_before_prints_observers_and_next_setup(self):
        for policy, sync in (('futex-early', 'futex'), ('futex-early-both', 'futex'), ('preseed', 'pipe')):
            for workload in ('scan', 'lookup', 'parse', 'chase', 'deflate'):
                with self.subTest(policy=policy, workload=workload):
                    run, events = self.run_benchmark(policy, sync, workload)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertIn('PIPE_HINT_HOST_VERIFY_PASS', run.stdout)
                    self.assertEqual(run.stdout.count('PIPE_HINT_HOST_VERIFY_SCOPE '), 1)
                    self.assertNotRegex(run.stdout, r'^PIPE_HINT_(?:SCOPE|RESULT|WHOLE|PASS)\b')
                    owner = events[0]['pid']
                    parent = [event for event in events if event['pid'] == owner]
                    for event in parent:
                        if event['name'] in ('print', 'puts', 'usage', 'setup_mmap', 'setup_pipe'):
                            self.assertEqual((event['mode'], event['pending']), (0, 0), event)
                    # A startup reset precedes observers, then each cell resets
                    # only after the child has been reaped and parent data freed.
                    self.assertEqual(parent[0]['name'], 'mode')
                    resets = [i for i,e in enumerate(parent) if e['name']=='mode' and e['value']==0]
                    # Existing disabled-cell setup also writes mode zero for
                    # futex policies. Cleanup resets follow workload frees.
                    self.assertEqual(len(resets), 7 if sync == 'futex' else 5)
                    cleanup = [i for i in resets if i and parent[i-1]['name']=='free']
                    self.assertEqual(len(cleanup), 4)
                    for position in cleanup:
                        earlier = parent[:position]
                        reap = max(i for i,e in enumerate(earlier) if e['name']=='reap' and e['value']>0)
                        free = max(i for i,e in enumerate(earlier) if e['name']=='free')
                        self.assertLess(reap, free)
                    for i,event in enumerate(parent):
                        if event['name']=='print' and event['value']==1:
                            # The final preceding cycle sample is whole_end.
                            clock = next(e for e in reversed(parent[:i]) if e['name']=='clock')
                            self.assertEqual((clock['mode'],clock['pending']), (0,0))

    def test_queued_cleanup_drain_cost_is_inside_whole_timer(self):
        run, _ = self.run_benchmark(flags={'BP_SCOPE_POLL_DELAY': '1'})
        self.assertEqual(run.returncode, 0, run.stderr)
        steady = {tuple(map(int, row[:3])): int(row[3]) for row in re.findall(
            r'HOST_VERIFY_RESULT repeat=(\d+) order=(\d+) enabled=(\d) cycles=(\d+)', run.stdout)}
        whole = {tuple(map(int, row[:3])): int(row[3]) for row in re.findall(
            r'HOST_VERIFY_WHOLE repeat=(\d+) order=(\d+) enabled=(\d) cycles=(\d+)', run.stdout)}
        for key in whole:
            if key[2]:
                self.assertGreaterEqual(whole[key] - steady[key], 6000000)

    def test_never_drained_or_failed_prctl_cannot_emit_pass(self):
        for flags, error in (({'BP_SCOPE_NEVER_DRAIN':'1'}, 'prefix-controller drain'),
                             ({'BP_SCOPE_RESET_FAIL':'1'}, 'preview mode'),
                             ({'BP_SCOPE_STATUS_FAIL':'1'}, 'instruction-prefix status')):
            with self.subTest(flags=flags):
                run, events = self.run_benchmark(flags=flags)
                self.assertEqual(run.returncode, 1, run.stderr)
                self.assertIn(error, run.stderr)
                self.assertNotIn('HOST_VERIFY_PASS', run.stdout)
                self.assertNotRegex(run.stdout, r'HOST_VERIFY_WHOLE .*enabled=1')
                if 'BP_SCOPE_NEVER_DRAIN' in flags:
                    last_reset = max(i for i,e in enumerate(events) if e['name']=='mode' and e['value']==0)
                    self.assertEqual(sum(e['name']=='poll' for e in events[last_reset+1:]), 4096)

    def test_new_make_targets_enable_scope_without_altering_existing_recipes(self):
        for flavor in ('plain', 'zlib'):
            run = subprocess.run(['make','--no-print-directory','-n','-C',str(HERE),
                                  'emit-pipe-hint-benchmark-' + flavor + '-scoped-resources-compressed-transfer',
                                  'BP_LINUX_DYNAMIC_CC=/bin/true','OUT='+str(self.root/'make-only')],
                                 capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn('-DBP_RESUME_COMPLETE_POLICY_SCOPE=1',run.stdout)
            self.assertIn('-DBP_RESUME_RESOURCE_STATS=1',run.stdout)
            self.assertEqual('-lz' in run.stdout,flavor=='zlib')
            self.assertIn('emit_resume_transfer.py',run.stdout)

    def test_explicit_zero_scope_preserves_existing_host_variant_bytes(self):
        for zlib in (False, True):
            for resources in (False, True):
                values = []
                for defined in (False, True):
                    binary = self.root / ('zero-%d-%d-%d' % (zlib, resources, defined))
                    command = [self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-DBP_RESUME_HOST_VERIFY=1']
                    command += ['-DBP_RESUME_RESOURCE_STATS=1'] if resources else []
                    command += ['-DBP_RESUME_ZLIB=1'] if zlib else []
                    command += ['-DBP_RESUME_COMPLETE_POLICY_SCOPE=0'] if defined else []
                    command += [str(HERE/'scheduler_pipe_hint_benchmark.c'),'-o',str(binary)]
                    command += ['-lz'] if zlib else []
                    subprocess.run(command,check=True,capture_output=True,timeout=30)
                    values.append(hashlib.sha256(binary.read_bytes()).digest())
                self.assertEqual(*values)

    def test_scope_requires_whole_cell_resource_timing(self):
        run = subprocess.run([self.cc, '-std=c11', '-DBP_RESUME_HOST_VERIFY=1',
                              '-DBP_RESUME_COMPLETE_POLICY_SCOPE=1', '-fsyntax-only',
                              str(HERE / 'scheduler_pipe_hint_benchmark.c')],
                             capture_output=True, text=True, timeout=20)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('Complete policy scope requires resource/whole-cell timing', run.stderr)

    def test_default_rv64_preprocessed_code_matches_archived_resource_source(self):
        archive = Path('/home/coyang/fpga-artifacts/context-resume/natural-demand-20261120/plain-resources')
        source = archive / 'scheduler_pipe_hint_benchmark.c'
        if not source.is_file():
            self.skipTest('archived pre-scope source is unavailable')
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         'b3322ac527cb95950f8a23869a01c5f3db4a8c25de59d4c324262b9eb31b2c55')
        variants = ((), ('BP_RESUME_ZLIB',), ('BP_RESUME_ZLIB','BP_RESUME_RETENTION'),
                    ('BP_RESUME_ZLIB','BP_RESUME_RESOURCE_STATS'), ('BP_RESUME_RESOURCE_STATS',),
                    ('BP_RESUME_ZLIB','BP_RESUME_RESOURCE_STATS','BP_RESUME_RETENTION'))
        for flags in variants:
            results = []
            for label, cu in (('old',source), ('new',HERE/'scheduler_pipe_hint_benchmark.c')):
                directory = self.root / ('cpp-' + label)
                directory.mkdir(exist_ok=True)
                (directory/'scheduler_pipe_hint_benchmark.c').write_bytes(cu.read_bytes())
                (directory/'resume_workload.h').write_bytes((HERE/'resume_workload.h').read_bytes())
                command = [self.cc,'-std=c11','-E','-P','-D__riscv=1','-D__riscv_xlen=64']
                command += ['-D'+flag+'=1' for flag in flags]
                command += ['scheduler_pipe_hint_benchmark.c']
                result = subprocess.run(command,cwd=directory,capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,0,result.stderr)
                results.append(result.stdout)
            self.assertEqual(*results, 'default-off C differs for flags '+str(flags))


if __name__ == '__main__':
    unittest.main()
