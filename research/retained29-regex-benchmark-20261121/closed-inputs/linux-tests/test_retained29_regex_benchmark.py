"""Real POSIX library/fork checks using the unchanged shared ABI29 mock only."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import test_retained29_benchmark as protocol_test
from test_resume_resource_accounting import MOCK as RESOURCE_MOCK, EXPECTED

HERE = Path(__file__).resolve().parent
REGEX_MOCK = r'''
#include <regex.h>
static regex_t *compiled_regex[3];
static unsigned compiled_count;
static void regex_pause(void) {
    if(getenv("R29_REGEX_DELAY")) {
        struct timespec pause={.tv_nsec=2000000};
        while(nanosleep(&pause,&pause) && errno==EINTR) {}
    }
}
int __real_regcomp(regex_t *,const char *,int);
int __wrap_regcomp(regex_t *r,const char *pattern,int flags) {
    unsigned p=compiled_count++%3;
    compiled_regex[p]=r;event("regex_compile",p);
    if((isfault("regex-child-compile") && getpid()!=owner) ||
       (isfault("regex-parent-compile") && getpid()==owner)) pattern="[";
    int result=__real_regcomp(r,pattern,flags);regex_pause();return result;
}
/* Independent schema parser checks actual POSIX answers and all capture spans.
 * It does not use the module's generated class/hash metadata or regex results
 * as its oracle. The tested log grammar has exactly four space-separated fields.
 */
static int schema(const char *s,size_t starts[5],size_t ends[5]) {
    static const char *keys[]={"id=","user=","status=","bytes="};
    size_t offset=0;starts[0]=0;ends[0]=strlen(s);
    for(unsigned n=0;n<4;++n) {
        size_t keylen=strlen(keys[n]);
        if(strncmp(s+offset,keys[n],keylen)) return 0;
        offset+=keylen;starts[n+1]=offset;
        while(s[offset] && s[offset]!=' ') ++offset;
        ends[n+1]=offset;
        if(n<3) {if(s[offset]!=' ') return 0;++offset;}
        else if(s[offset]) return 0;
    }
    size_t id=ends[1]-starts[1],user=ends[2]-starts[2],bytes=ends[4]-starts[4];
    if(id<1||id>6||user<3||user>8||bytes<1||bytes>5) return 0;
    for(unsigned n=1;n<=4;++n) if(n!=3) for(size_t k=starts[n];k<ends[n];++k)
        if(n==2 ? (s[k]<'a'||s[k]>'z') : (s[k]<'0'||s[k]>'9')) return 0;
    size_t len=ends[3]-starts[3];const char *status=s+starts[3];
    if(len==2 && !memcmp(status,"ok",2)) return 1;
    if(len==4 && !memcmp(status,"warn",4)) return 3;
    if(len==4 && !memcmp(status,"fail",4)) return 7;
    return 0;
}
int __real_regexec(const regex_t *,const char *,size_t,regmatch_t [],int);
int __wrap_regexec(const regex_t *r,const char *s,size_t n,regmatch_t m[],int flags) {
    unsigned p=0;while(p<3 && compiled_regex[p]!=r) ++p;
    if(p==3 || n!=5 || flags) _exit(101);
    int result=__real_regexec(r,s,n,m,flags);
    size_t start[5],end[5];int expected=!!(schema(s,start,end)&(1<<p));
    if((result!=0 && result!=REG_NOMATCH) || (!result)!=expected) _exit(102);
    if(!result) for(unsigned g=0;g<5;++g)
        if(m[g].rm_so!=(regoff_t)start[g] || m[g].rm_eo!=(regoff_t)end[g]) _exit(103);
    event("regex_exec",!result);
    if((isfault("regex-child-exec") && getpid()!=owner) ||
       (isfault("regex-parent-exec") && getpid()==owner)) return REG_ESPACE;
    if(!result && isfault("regex-bad-capture")) m[1].rm_eo=(regoff_t)strlen(s)+1;
    if(!result && isfault("regex-wrong-checksum")) ++m[1].rm_so;
    return result;
}
void __real_regfree(regex_t *);
void __wrap_regfree(regex_t *r) {event("regex_free",0);__real_regfree(r);regex_pause();}
void *__real_malloc(size_t);
void *__wrap_malloc(size_t size) {event("allocation",size);return __real_malloc(size);}
'''


class RegexBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="retained29-regex-benchmark-", dir="/dev/shm")
        cls.root = Path(cls.tmp.name)
        mock = cls.root / "mock.c"
        mock.write_text(RESOURCE_MOCK.replace("int __wrap_getrusage(", "int deterministic_getrusage(")
                        + protocol_test.MOCK + REGEX_MOCK)
        cls.binary = cls.root / "benchmark"
        command = [os.environ.get("BP_HOST_CC", "cc"), "-O2", "-Wall", "-Wextra", "-Werror", "-std=c11",
                   "-DBP_RETAINED29_HOST_VERIFY=1", str(HERE / "scheduler_retained29_regex_benchmark.c"),
                   str(mock), "-o", str(cls.binary)]
        command += ["-Wl,--wrap=" + name for name in ("prctl", "fork", "waitpid", "free", "munmap",
                    "getrusage", "calloc", "malloc", "printf", "puts", "regcomp", "regexec", "regfree")]
        if os.environ.get("R29_REGEX_SANITIZE"):
            command += ["-O1", "-g", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie", "-fsanitize=address,undefined"]
        result = subprocess.run(command, text=True, capture_output=True, timeout=60)
        if result.returncode: raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, **kwargs):
        kwargs.setdefault("workload", "regex")
        env = dict(kwargs.get("resource") or {}, LC_ALL="C")
        kwargs["resource"] = env
        return protocol_test.Retained29BenchmarkTests.run_case(self, **kwargs)

    fail_closed = protocol_test.Retained29BenchmarkTests.fail_closed

    def test_all_masks_transports_real_library_calls_captures_and_resources(self):
        for policy, mask in (("ordinary-i",9),("ordinary-d",6),("ordinary-joint",15),
                             ("advisory-i",1),("advisory-d",2),("advisory-joint",3)):
            for sync in ("pipe", "futex"):
                with self.subTest(policy=policy, sync=sync):
                    run, events = self.run_case(policy=policy, sync=sync)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertIn("RESUME_RETAINED29_REGEX_HOST_VERIFY_PASS", run.stdout)
                    self.assertNotIn("RESUME_RETAINED29_HOST_VERIFY_", run.stdout)
                    self.assertNotIn("RESUME_RETAINED29_REGEX_PASS", run.stdout)
                    self.assertIn("workload=regex advisory_source=none", run.stdout)
                    self.assertEqual([v for n,_,v in events if n=="r29_control"], [0,0,mask,0,mask,0,0,0])
                    self.assertTrue(all(v==0 for n,_,v in events if n in ("task_mode","report","final_mode")))
                    counts = {}
                    for name,pid,value in events:
                        if name=="regex_exec":
                            counts.setdefault(pid,[0,0])[value] += 1
                    self.assertEqual(len(counts),5)
                    self.assertEqual(sorted(sum(v) for v in counts.values()),[320]*4+[1280])
                    self.assertTrue(all(all(v) for v in counts.values()))
                    self.assertEqual(sum(n=="regex_compile" for n,_,_ in events),24)
                    self.assertEqual(sum(n=="regex_free" for n,_,_ in events),24)
                    for row in re.findall(r"_RESOURCE .*",run.stdout):
                        values=dict((k,int(v)) for k,v in re.findall(r"(\w+)=(\d+)",row))
                        for field,expected in EXPECTED.items():self.assertEqual(values[field],expected)

    def test_compile_free_are_inside_matched_whole_and_control_lifecycle(self):
        run,events=self.run_case(resource={"R29_REGEX_DELAY":"1"})
        self.assertEqual(run.returncode,0,run.stderr)
        starts=[n for n,e in enumerate(events) if e[0]=="usage" and e[2]%4==1]
        for index,begin in enumerate(starts):
            end=next(n for n in range(begin+1,len(events)) if events[n][0]=="usage" and events[n][2]==4*(index+1))
            cell=events[begin:end+1]
            control=[n for n,e in enumerate(cell) if e[0]=="r29_control"]
            library=[n for n,e in enumerate(cell) if e[0] in ("regex_compile","regex_exec","regex_free")]
            self.assertEqual(len(control),2)
            self.assertLess(control[0],min(library));self.assertGreater(control[-1],max(library))
            self.assertEqual(sum(e[0]=="regex_free" for e in cell),6)
            self.assertFalse(any(e[0]=="report" for e in cell))
        steady=list(map(int,re.findall(r"_RESULT .*?cycles=(\d+)",run.stdout)))
        whole=list(map(int,re.findall(r"_WHOLE .*?cycles=(\d+)",run.stdout)))
        self.assertTrue(all(a-b>=12000000 for a,b in zip(whole,steady)))

    def test_larger_private_corpus_and_optional_leg_observers(self):
        run,_=self.run_case(kib=128,profile="legs",resource={"R29_REAL_USAGE":"1"})
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(run.stdout.count("_LEGS "),4)
        self.assertEqual(run.stdout.count("_WHOLE "),4)
        for row in re.findall(r"_RESOURCE .*",run.stdout):
            self.assertGreater(int(re.search(r"minor_faults=(\d+)",row)[1]),0)

    def test_library_or_checksum_errors_fail_and_reset(self):
        for fault in ("regex-child-compile","regex-parent-compile","regex-child-exec",
                      "regex-parent-exec","regex-bad-capture","regex-wrong-checksum"):
            with self.subTest(fault=fault):
                run,events=self.run_case(fault=fault)
                self.fail_closed(run)
                self.assertEqual([v for n,_,v in events if n=="final_mode"],[0])

    def test_existing_protocol_faults_stay_fail_closed(self):
        for fault in ("absent","reserved","initial-active","busy","prefix-activity",
                      "replay-activity","child-allocation","parent-allocation","bad-reset"):
            run,_=self.run_case(fault=fault)
            self.fail_closed(run)

    def test_regex_only_cli_rejects_other_work_and_sizes_before_control(self):
        for changes in (("32","scan","none"),("64","regex","none"),("0","regex","none"),
                        ("32","regex","mode14"),("129","regex","none")):
            run,events=self.run_case(arguments=["3","2","ordinary-joint","2","futex","plain",*changes])
            self.assertEqual(run.returncode,2,run.stderr)
            self.assertFalse(any(n in ("r29_control","allocation","regex_compile") for n,_,_ in events))


if __name__ == "__main__":unittest.main()
