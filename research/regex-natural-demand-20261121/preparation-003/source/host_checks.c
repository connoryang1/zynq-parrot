#define _POSIX_C_SOURCE 200809L
#include "regex_workload.h"
#include <assert.h>
#include <locale.h>
#include <stdio.h>
#include <string.h>

static void closed(size_t bytes, uint32_t seed) {
    rw_test_reset(); rw_workload *w = NULL; rw_result r[RW_PATTERNS]; rw_memory m;
    assert(rw_create(&w, bytes, seed) == RW_OK); assert(w);
    assert(rw_memory_usage(w, &m) == RW_OK);
    assert(m.input_bytes == bytes && m.corpus_storage_bytes == bytes + m.blocks);
    assert(rw_verify(w, 0) == RW_OK);
    for (unsigned i = 0; i < 37; ++i) assert(rw_request(w, r) == RW_OK);
    assert(rw_verify(w, 37) == RW_OK && rw_verify(w, 36) == RW_CORRUPT);
    rw_destroy(&w); rw_destroy(&w); assert(!w);
    assert(rw_test_live_owned() == 0 && rw_test_compiles() == 3 && rw_test_frees() == 3);
}
int main(void) {
    assert(setlocale(LC_ALL, "C"));
    const size_t sizes[] = {0, 1, 31, 67, 4095, 4096, 4097, 8193, 32768, 32769, RW_MAX_CORPUS_BYTES};
    for (unsigned i = 0; i < sizeof(sizes)/sizeof(sizes[0]); ++i)
        for (unsigned seed = 0; seed < 4; ++seed) closed(sizes[i], seed * 197u);
    for (int fail = 1; fail <= 3; ++fail) {
        rw_workload *w = NULL; rw_test_reset(); rw_test_fail_allocation(fail);
        assert(rw_create(&w, 8193, 7) == RW_MEMORY && !w && rw_test_live_owned() == 0);
    }
    for (int fail = 0; fail < 3; ++fail) {
        rw_workload *w = NULL; rw_test_reset(); rw_test_fail_compile(fail);
        assert(rw_create(&w, 8193, 7) == RW_LIBRARY && !w);
        assert(rw_test_compiles() == (unsigned)fail && rw_test_frees() == (unsigned)fail && !rw_test_live_owned());
    }
    for (int fail = 0; fail < 3; ++fail) {
        rw_workload *w = NULL; rw_result r[RW_PATTERNS]; rw_test_reset();
        assert(rw_create(&w, 8193, 7) == RW_OK); rw_test_fail_execution(fail);
        assert(rw_request(w, r) == RW_LIBRARY && rw_request(w, r) == RW_POISONED);
        assert(rw_verify(w, 0) == RW_CORRUPT); rw_destroy(&w);
        assert(!rw_test_live_owned() && rw_test_frees() == 3);
    }
    for (int sentinel = 0; sentinel < 2; ++sentinel) {
        rw_workload *w = NULL; rw_result r[RW_PATTERNS]; size_t n; rw_test_reset();
        assert(rw_create(&w, 8193, 7) == RW_OK);
        char *s = (char *)rw_block(w, 0, &n); assert(s && n);
        if (sentinel) s[n] = 'x';
        else { char *row = strstr(s, "id="); assert(row); row[0] = 'x'; }
        assert(rw_request(w, r) == RW_CORRUPT && rw_verify(w, 0) == RW_CORRUPT);
        rw_destroy(&w); assert(!rw_test_live_owned());
    }
    /* Even corruption in nonmatched padding is caught by mandatory close. */
    rw_workload *w = NULL; rw_result r[RW_PATTERNS]; size_t n; rw_test_reset();
    assert(rw_create(&w, 8193, 7) == RW_OK); char *tail = (char *)rw_block(w, 2, &n); assert(n == 1);
    tail[0] = '!'; assert(rw_request(w, r) == RW_OK); assert(rw_verify(w, 1) == RW_CORRUPT);
    rw_destroy(&w); assert(!rw_test_live_owned());
    assert(rw_create(NULL, 10, 0) == RW_ARGUMENT);
    assert(rw_create(&w, RW_MAX_CORPUS_BYTES + 1, 0) == RW_ARGUMENT && !w);
    assert(rw_create(&w, 8193, 7) == RW_OK); rw_workload *original = w;
    assert(rw_create(&w, 8193, 7) == RW_ARGUMENT && w == original);
    assert(rw_request(NULL, r) == RW_ARGUMENT && rw_request(w, NULL) == RW_ARGUMENT);
    assert(rw_block(w, 3, &n) == NULL && rw_pattern(3) == NULL);
    rw_destroy(&w); assert(!rw_test_live_owned());
    if (setlocale(LC_CTYPE, "C.UTF-8")) {
        assert(rw_create(&w, 8193, 7) == RW_ARGUMENT && !w);
        assert(setlocale(LC_ALL, "C"));
    }
    puts("REGEX_CORE_HOST_CHECKS_PASS"); return 0;
}
