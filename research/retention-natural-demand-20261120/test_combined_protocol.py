"""Verify actual retention/resource/scope flags with existing real-fork mocks."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'linux-tests'))
from test_resume_complete_policy_scope import MOCK as SCOPE_MOCK

MOCK = SCOPE_MOCK.replace(
    'struct controller { _Atomic unsigned pending, armed; };',
    'struct controller { _Atomic unsigned pending, armed, retained_mode; };')
OLD = 'if (getpid() == owner && (mode || atomic_load(&controller->pending))) _exit(93);'
assert MOCK.count(OLD) == 1
MOCK = MOCK.replace(OLD,
    'if (getpid() == owner && (mode || atomic_load(&controller->pending) || '
    'atomic_load(&controller->retained_mode))) _exit(93);\n'
    '    if (getpid() == owner) event("retention_idle", atomic_load(&controller->retained_mode));')
MOCK += r'''
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
'''


class CombinedProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='retention-natural-host-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.mock = cls.directory/'combined.c'
        cls.mock.write_text(MOCK)
        cls.binary = cls.directory/'combined'
        flags = ['-DBP_RESUME_HOST_VERIFY=1', '-DBP_RESUME_RETENTION=1',
                 '-DBP_RESUME_RESOURCE_STATS=1', '-DBP_RESUME_COMPLETE_POLICY_SCOPE=1']
        command = [os.environ.get('BP_HOST_CC', 'cc'), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror']+flags
        command += [str(ROOT/'linux-tests/scheduler_pipe_hint_benchmark.c'), str(cls.mock), '-o', str(cls.binary)]
        command += ['-Wl,--wrap='+name for name in ('prctl','syscall','fork','mmap','pipe','waitpid',
                    'free','munmap','getrusage','clock_gettime','printf','puts','fflush')]
        subprocess.run(command, check=True, capture_output=True, timeout=30)

    def run_case(self, policy='retention-rr', sync='futex', workload='lookup', flags=None):
        log = self.directory/('events-'+str(len(list(self.directory.glob('events-*')))))
        env = dict(os.environ, BP_SCOPE_LOG=str(log))
        env.update(flags or {})
        selected = min(os.sched_getaffinity(0))
        run = subprocess.run([str(self.binary),'3','2',policy,'2',sync,'plain','32',workload],
            env=env, text=True, capture_output=True, timeout=15,
            preexec_fn=lambda: os.sched_setaffinity(0, {selected}))
        events = [dict(name=n,pid=int(p),mode=int(m),pending=int(q),value=int(v))
            for n,p,m,q,v in re.findall(r'^(\w+) pid=(\d+) mode=(\d+) pending=(\d+) value=(-?\d+)$',
                                       log.read_text(), re.M)]
        return run, events

    def check_complete(self, run, events, mode):
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('PIPE_HINT_HOST_VERIFY_PASS', run.stdout)
        self.assertNotRegex(run.stdout, re.compile(r'^PIPE_HINT_(?:RESULT|WHOLE|RESOURCE|RETENTION|SCOPE) ', re.M))
        self.assertEqual(run.stdout.count('PIPE_HINT_HOST_VERIFY_SCOPE '), 1)
        rows = re.findall(r'^PIPE_HINT_HOST_VERIFY_(RESULT|WHOLE|RETENTION|RESOURCE) repeat=(\d+) order=(\d+) enabled=(\d+)',run.stdout,re.M)
        self.assertEqual([r[0] for r in rows], ['RESULT','WHOLE','RETENTION','RESOURCE']*4)
        self.assertEqual([int(r[3]) for r in rows[::4]], [0,1,1,0])
        whole = [int(n) for n in re.findall(r'^PIPE_HINT_HOST_VERIFY_WHOLE .* cycles=(\d+) ',run.stdout,re.M)]
        steady = [int(n) for n in re.findall(r'^PIPE_HINT_HOST_VERIFY_RESULT .* cycles=(\d+) ',run.stdout,re.M)]
        self.assertTrue(all(a>=b for a,b in zip(whole,steady)))
        statuses = re.findall(r'^PIPE_HINT_HOST_VERIFY_RETENTION .* capability=(\d+) mode=(\d+) ',run.stdout,re.M)
        self.assertEqual(statuses,[('1','0'),('1',str(mode)),('1',str(mode)),('1','0')])
        controls = [e['value'] for e in events if e['name']=='retention_control']
        self.assertEqual(controls,[0,0,mode,0,mode,0,0,0])
        self.assertTrue(all(e['value']==0 for e in events if e['name']=='retention_idle'))
        self.assertFalse(any(e['value'] for e in events if e['name']=='mode'))
        self.assertFalse(any(e['name']=='hint' for e in events))
        outside = [e for e in events if e['name'] in ('setup_mmap','setup_pipe','usage','print','puts')]
        self.assertTrue(outside)
        self.assertTrue(all(e['mode']==e['pending']==0 for e in outside))
        self.assertEqual(len([e for e in events if e['name']=='usage']),16)
        return whole, steady

    def test_actual_three_flags_both_policies_transports_and_four_plain_workloads(self):
        for policy,mode in (('retention-rr',1),('retention-first',2)):
            for sync in ('pipe','futex'):
                for workload in ('scan','lookup','parse','chase'):
                    with self.subTest(policy=policy,sync=sync,workload=workload):
                        run,events=self.run_case(policy,sync,workload)
                        self.check_complete(run,events,mode)

    def test_all_four_reported_prefix_pending_bits_are_polled_and_global_reset_precedes_observers(self):
        run,events=self.run_case()
        self.check_complete(run,events,1)
        mask=(1<<1)|(1<<2)|(1<<3)|(1<<54)
        self.assertEqual({e['value']&mask for e in events if e['name']=='poll'},
                         {0,1<<1,1<<2,1<<3,1<<54})
        for i,e in enumerate(events):
            if e['name']=='usage' and sum(v['name']=='usage' for v in events[:i])%4==2:
                prior=events[:i]
                reset=max(j for j,v in enumerate(prior) if v['name']=='retention_control')
                self.assertEqual(prior[reset]['value'],0)
                self.assertTrue(any(v['name']=='retention_status' and v['value']==0 for v in prior[reset+1:]))
                self.assertTrue(any(v['name']=='poll' and v['value']&mask==0 for v in prior[reset+1:]))

    def test_mock_pending_cleanup_cost_is_inside_both_arms_whole(self):
        run,events=self.run_case(flags={'BP_SCOPE_POLL_DELAY':'1'})
        whole,steady=self.check_complete(run,events,1)
        self.assertTrue(all(a-b>=8_000_000 for a,b in zip(whole,steady)))

    def test_combined_prefix_and_retention_failures_never_pass(self):
        for flag in ('BP_SCOPE_RESET_FAIL','BP_SCOPE_STATUS_FAIL','BP_SCOPE_NEVER_DRAIN',
                     'BP_COMBINED_OLD','BP_COMBINED_SET_FAIL'):
            with self.subTest(flag=flag):
                run,_=self.run_case(flags={flag:'1'})
                self.assertNotEqual(run.returncode,0)
                self.assertNotIn('PIPE_HINT_HOST_VERIFY_PASS',run.stdout)
                self.assertNotIn('PIPE_HINT_PASS',run.stdout)


if __name__=='__main__':
    unittest.main()
