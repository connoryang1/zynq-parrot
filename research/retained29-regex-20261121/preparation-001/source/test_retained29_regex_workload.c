#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <locale.h>
#include <regex.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned allocations, live_owned, compiles, successful_compiles, executions, frees;
static unsigned fail_allocation, fail_compile, fail_execution, bad_capture;

static void *test_malloc(size_t n)
{
	if (++allocations == fail_allocation) return NULL;
	void *p = malloc(n); if (p) ++live_owned; return p;
}

static void *test_calloc(size_t n, size_t s)
{
	if (++allocations == fail_allocation) return NULL;
	void *p = calloc(n, s); if (p) ++live_owned; return p;
}

static void test_free(void *p)
{
	if (p) { assert(live_owned); --live_owned; }
	free(p);
}

static int test_regcomp(regex_t *r, const char *pattern, int flags)
{
	++compiles;
	int error = regcomp(r, compiles == fail_compile ? "[" : pattern, flags);
	if (!error) ++successful_compiles;
	return error;
}

static int test_regexec(const regex_t *r, const char *s, size_t n, regmatch_t m[], int flags)
{
	++executions;
	int error = regexec(r, s, n, m, flags);
	if (executions == fail_execution) return REG_ESPACE;
	if (!error && bad_capture) { m[1].rm_eo = (regoff_t)strlen(s) + 1; bad_capture = 0; }
	return error;
}

static void test_regfree(regex_t *r) { ++frees; regfree(r); }
#define malloc test_malloc
#define calloc test_calloc
#define free test_free
#define regcomp test_regcomp
#define regexec test_regexec
#define regfree test_regfree
#include "retained29_regex_workload.h"
#undef malloc
#undef calloc
#undef free
#undef regcomp
#undef regexec
#undef regfree

static void reset_hooks(void)
{
	assert(!live_owned);
	allocations = compiles = successful_compiles = executions = frees = 0;
	fail_allocation = fail_compile = fail_execution = bad_capture = 0;
}

static void finish(struct retained29_regex_workload *w)
{
	retained29_regex_free(w); retained29_regex_free(w);
	assert(!live_owned && frees == successful_compiles);
	assert(!w->compiled && !w->corpus && !w->record);
}

static void normal_cases(void)
{
	const uint64_t seeds[] = {0, 1, 73, UINT64_C(0x123456789abcdef0), UINT64_MAX};
	for (unsigned kib = 32; kib <= 128; kib *= 4)
		for (unsigned seed = 0; seed < sizeof(seeds)/sizeof(seeds[0]); ++seed) {
			reset_hooks(); struct retained29_regex_workload w;
			assert(retained29_regex_init(&w, kib, seeds[seed]) == 0);
			assert(compiles == 3 && successful_compiles == 3 && live_owned == 2);
			assert(w.bytes == (size_t)kib * 1024 && w.records > 100);
			assert(retained29_regex_check_total(&w, 0));
			uint64_t total = 0;
			for (unsigned request = 0; request < 37; ++request) {
				total += retained29_regex_run(&w);
				assert(w.calls == (uint64_t)(request + 1) * 64);
				assert(executions == w.calls && compiles == 3);
				assert(retained29_regex_check_total(&w, total));
				assert(!retained29_regex_check_total(&w, total + 1));
			}
			assert(w.positive_calls && w.negative_calls && !w.error);
			assert(w.runs == 37 && executions == 37 * 64);
			finish(&w);
		}
}

static void failures(void)
{
	for (unsigned allocation = 1; allocation <= 2; ++allocation) {
		reset_hooks(); fail_allocation = allocation;
		struct retained29_regex_workload w;
		assert(retained29_regex_init(&w, 32, 7) == -1 && errno == ENOMEM);
		finish(&w);
	}
	for (unsigned pattern = 1; pattern <= 3; ++pattern) {
		reset_hooks(); fail_compile = pattern;
		struct retained29_regex_workload w;
		assert(retained29_regex_init(&w, 32, 7) == -1 && errno == EIO);
		assert(compiles == pattern && successful_compiles == pattern - 1);
		finish(&w);
	}
	for (unsigned call = 1; call <= 64; call *= 8) {
		reset_hooks(); struct retained29_regex_workload w;
		assert(!retained29_regex_init(&w, 32, 7));
		fail_execution = call;
		assert(retained29_regex_run(&w) == UINT64_MAX && w.error);
		assert(executions == call && w.calls == call && !w.runs);
		assert(!retained29_regex_check_total(&w, UINT64_MAX));
		assert(retained29_regex_run(&w) == UINT64_MAX && executions == call);
		finish(&w);
	}
	reset_hooks(); struct retained29_regex_workload w;
	assert(!retained29_regex_init(&w, 32, 7));
	bad_capture = 1;
	assert(retained29_regex_run(&w) == UINT64_MAX && w.error);
	assert(!retained29_regex_check_total(&w, UINT64_MAX));
	finish(&w);
}

static void corruption(void)
{
	for (unsigned mode = 0; mode < 5; ++mode) {
		reset_hooks(); struct retained29_regex_workload w;
		assert(!retained29_regex_init(&w, 32, 7));
		uint64_t total = retained29_regex_run(&w);
		assert(retained29_regex_check_total(&w, total));
		size_t selected = retained29_regex_mix(w.seed + w.runs * 64) % w.records;
		struct retained29_regex_record *r = &w.record[selected];
		if (mode == 0) w.corpus[w.bytes - 1] ^= 1; /* includes never queried padding */
		if (mode == 1) w.record[0].capture_hash ^= 1; /* generated oracle metadata */
		if (mode == 2) w.corpus[r->offset + r->length] = 'x';
		if (mode == 3) r->offset = (uint32_t)w.bytes + 1;
		if (mode == 4) w.corpus[w.record[0].offset] = 'I';
		assert(!retained29_regex_check_total(&w, total));
		if (mode == 2 || mode == 3) {
			unsigned before = executions;
			assert(retained29_regex_run(&w) == UINT64_MAX && w.error);
			assert(executions == before); /* stops before unsafe library access */
		}
		finish(&w);
	}
}

static void inherited_private_state(void)
{
	reset_hooks(); struct retained29_regex_workload w;
	assert(!retained29_regex_init(&w, 32, 991));
	uint64_t total = retained29_regex_run(&w);
	total += retained29_regex_run(&w);
	assert(retained29_regex_check_total(&w, total));
	pid_t child = fork(); assert(child >= 0);
	if (!child) {
		total += retained29_regex_run(&w);
		assert(retained29_regex_check_total(&w, total));
		finish(&w);
		reset_hooks(); assert(!retained29_regex_init(&w, 128, 992));
		total = retained29_regex_run(&w);
		assert(retained29_regex_check_total(&w, total)); finish(&w);
		_exit(0);
	}
	int status;
	assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && !WEXITSTATUS(status));
	assert(w.runs == 2 && executions == 128 && retained29_regex_check_total(&w, total));
	finish(&w);
}

int main(void)
{
	assert(setlocale(LC_ALL, "C"));
	normal_cases(); failures(); corruption(); inherited_private_state();
	reset_hooks(); struct retained29_regex_workload w;
	for (unsigned kib = 0; kib <= 129; ++kib) {
		if (kib == 32 || kib == 128) continue;
		assert(retained29_regex_init(&w, kib, 1) == -1 && errno == EINVAL);
		finish(&w);
	}
	assert(retained29_regex_init(NULL, 32, 1) == -1);
	assert(retained29_regex_run(NULL) == UINT64_MAX);
	assert(!retained29_regex_check_total(NULL, 0));
	retained29_regex_free(NULL);
	const char *utf8 = setlocale(LC_ALL, "C.UTF-8");
	if (utf8) {
		char before[128];
		assert(strlen(utf8) < sizeof(before)); strcpy(before, utf8);
		assert(retained29_regex_init(&w, 32, 1) == -1 && errno == EINVAL);
		assert(!strcmp(setlocale(LC_ALL, NULL), before));
		finish(&w);
	}
	assert(setlocale(LC_ALL, "C"));
	puts("RETAINED29_REGEX_HOST_PASS");
	return 0;
}
