#define _POSIX_C_SOURCE 200809L
#include "regex_workload.h"
#include <errno.h>
#include <inttypes.h>
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int number(const char *s, uint64_t *out) {
    char *end; errno = 0;
    if (!s[0] || s[0] == '-') return 0;
    unsigned long long n = strtoull(s, &end, 10);
    if (errno || *end) return 0;
    *out = (uint64_t)n; return 1;
}
int main(int argc, char **argv) {
    int dump = argc > 1 && !strcmp(argv[1], "--dump");
    uint64_t bytes = 32769, seed = 71, requests = 17;
    if (dump) { --argc; ++argv; }
    if ((argc != 1 && argc != 4 && !(dump && argc == 3)) ||
        (argc > 1 && (!number(argv[1], &bytes) || !number(argv[2], &seed))) ||
        (argc == 4 && !number(argv[3], &requests)) ||
        bytes > RW_MAX_CORPUS_BYTES || seed > UINT32_MAX || requests > 4096) return 2;
    if (!setlocale(LC_ALL, "C")) return 2;
    rw_workload *w = NULL; rw_memory memory; int status = rw_create(&w, (size_t)bytes, (uint32_t)seed);
    if (status) { fprintf(stderr, "REGEX_CORE_FAIL create=%d\n", status); return 1; }
    rw_memory_usage(w, &memory);
    printf("REGEX_CORE_META input=%zu blocks=%zu storage=%zu owned_metadata=%zu libc_internal=unmeasured\n",
           memory.input_bytes, memory.blocks, memory.corpus_storage_bytes, memory.owned_metadata_bytes);
    if (dump) {
        for (size_t b = 0; b < memory.blocks; ++b) {
            size_t length; const char *s = rw_block(w, b, &length);
            printf("REGEX_CORE_BLOCK %zu %zu ", b, length);
            for (size_t i = 0; i < length; ++i) printf("%02x", (unsigned char)s[i]);
            putchar('\n');
        }
        requests = 0;
    }
    for (uint64_t i = 0; i < requests; ++i) {
        rw_result result[RW_PATTERNS]; status = rw_request(w, result);
        if (status) break;
        printf("REGEX_CORE_ROW request=%" PRIu64 " block=%zu", i, (size_t)(i % memory.blocks));
        for (unsigned p = 0; p < RW_PATTERNS; ++p)
            printf(" count%u=%" PRIu64 " digest%u=%016" PRIx64, p, result[p].matches, p, result[p].checksum);
        putchar('\n');
    }
    if (!status) status = rw_verify(w, requests);
    rw_destroy(&w);
    if (status) { fprintf(stderr, "REGEX_CORE_FAIL validation=%d\n", status); return 1; }
    puts("REGEX_CORE_FUNCTIONAL_PASS"); return 0;
}
