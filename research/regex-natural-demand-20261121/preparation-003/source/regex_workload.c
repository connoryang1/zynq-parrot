#define _POSIX_C_SOURCE 200809L
#include "regex_workload.h"
#include <limits.h>
#include <locale.h>
#include <regex.h>
#include <stdlib.h>
#include <string.h>

static const char *const patterns[RW_PATTERNS] = {
    "^id=([0-9]{1,6}) user=([a-z]{3,8}) status=(ok|warn|fail) bytes=([0-9]{1,5})$",
    "^id=([0-9]{1,6}) user=([a-z]{3,8}) status=(warn|fail) bytes=([0-9]{1,5})$",
    "^id=([0-9]{1,6}) user=([a-z]{3,8}) status=(fail) bytes=([0-9]{1,5})$"
};
#define BASIS UINT64_C(14695981039346656037)
#define PRIME UINT64_C(1099511628211)

typedef struct {
    size_t offset, length;
    uint64_t input_hash;
    rw_result expected[RW_PATTERNS];
} rw_chunk;

struct rw_workload {
    regex_t regex[RW_PATTERNS];
    unsigned compiled;
    int poisoned;
    char *corpus;
    rw_chunk *chunks;
    size_t bytes, blocks, storage;
    uint64_t requests;
    rw_result totals[RW_PATTERNS];
};

#ifdef RW_TESTING
static int fail_alloc, allocations, fail_compile = -1, fail_execute = -1;
static size_t live_owned;
static unsigned compiles, frees;
void rw_test_reset(void) { fail_alloc = allocations = 0; fail_compile = fail_execute = -1; compiles = frees = 0; }
void rw_test_fail_allocation(int n) { fail_alloc = n; }
void rw_test_fail_compile(int n) { fail_compile = n; }
void rw_test_fail_execution(int n) { fail_execute = n; }
size_t rw_test_live_owned(void) { return live_owned; }
unsigned rw_test_compiles(void) { return compiles; }
unsigned rw_test_frees(void) { return frees; }
#endif

static void *owned_alloc(size_t bytes) {
#ifdef RW_TESTING
    if (++allocations == fail_alloc) return NULL;
#endif
    void *p = calloc(1, bytes);
#ifdef RW_TESTING
    if (p) ++live_owned;
#endif
    return p;
}
static void owned_free(void *p) {
    if (!p) return;
#ifdef RW_TESTING
    --live_owned;
#endif
    free(p);
}
static uint64_t hash_byte(uint64_t h, unsigned char c) { return (h ^ c) * PRIME; }
static uint64_t hash_number(uint64_t h, uint64_t v) {
    for (unsigned i = 0; i < 8; ++i) { h = hash_byte(h, (unsigned char)v); v >>= 8; }
    return h;
}
static uint64_t hash_text(const char *s, size_t n) {
    uint64_t h = BASIS;
    for (size_t i = 0; i < n; ++i) h = hash_byte(h, (unsigned char)s[i]);
    return h;
}
static void append(char *s, size_t *n, const char *text) {
    size_t len = strlen(text); memcpy(s + *n, text, len); *n += len;
}
static void decimal(char *s, size_t *n, uint32_t v) {
    char digits[10]; unsigned count = 0;
    do { digits[count++] = (char)('0' + v % 10u); v /= 10u; } while (v);
    while (count) s[(*n)++] = digits[--count];
}
static uint32_t mix(uint32_t x) {
    x ^= x >> 16; x *= UINT32_C(0x7feb352d); x ^= x >> 15;
    x *= UINT32_C(0x846ca68b); return x ^ (x >> 16);
}

/* Oracle construction consumes generator-known field boundaries and class,
 * never regexec, text parsing, actual request totals or regex capture output. */
static void generate(rw_workload *w, size_t block, uint32_t seed) {
    rw_chunk *c = &w->chunks[block]; char *dst = w->corpus + c->offset;
    size_t used = 0; uint32_t ordinal = 0;
    for (unsigned p = 0; p < RW_PATTERNS; ++p) c->expected[p].checksum = BASIS;
    while (used < c->length) {
        char row[128], user[9]; size_t n = 0, begin[5], end[5];
        uint32_t value = mix(seed ^ (uint32_t)(block * 65537u) ^ ordinal++);
        unsigned kind = value % 5u, userlen = 3u + (value >> 8) % 6u;
        for (unsigned i = 0; i < userlen; ++i) user[i] = (char)('a' + (value + i * 7u) % 26u);
        user[userlen] = 0; begin[0] = 0;
        /* One fifth of records are ordinary non-schema messages. */
        if (kind == 0) {
            append(row, &n, "note=ignored sequence="); decimal(row, &n, value % 1000000u);
        } else {
            append(row, &n, "id="); begin[1] = n; decimal(row, &n, value % 1000000u); end[1] = n;
            append(row, &n, " user="); begin[2] = n; append(row, &n, user); end[2] = n;
            append(row, &n, " status="); begin[3] = n;
            append(row, &n, kind == 1 ? "ok" : kind == 2 ? "warn" : "fail"); end[3] = n;
            append(row, &n, " bytes="); begin[4] = n; decimal(row, &n, (value >> 5) % 100000u); end[4] = n;
        }
        end[0] = n;
        if (n + 1 > c->length - used) break;
        memcpy(dst + used, row, n); dst[used + n] = '\n';
        if (kind) {
            for (unsigned p = 0; p < RW_PATTERNS; ++p) {
                if ((p == 1 && kind == 1) || (p == 2 && kind < 3)) continue;
                rw_result *r = &c->expected[p]; ++r->matches;
                for (unsigned g = 0; g < 5; ++g) {
                    r->checksum = hash_number(r->checksum, used + begin[g]);
                    r->checksum = hash_number(r->checksum, used + end[g]);
                    for (size_t i = begin[g]; i < end[g]; ++i) r->checksum = hash_byte(r->checksum, (unsigned char)row[i]);
                }
            }
        }
        used += n + 1;
    }
    memset(dst + used, '#', c->length - used); dst[c->length] = 0;
    c->input_hash = hash_text(dst, c->length);
}

void rw_destroy(rw_workload **wp) {
    if (!wp || !*wp) return;
    rw_workload *w = *wp;
    while (w->compiled) {
        regfree(&w->regex[--w->compiled]);
#ifdef RW_TESTING
        ++frees;
#endif
    }
    owned_free(w->chunks); owned_free(w->corpus); owned_free(w); *wp = NULL;
}

int rw_create(rw_workload **out, size_t bytes, uint32_t seed) {
    if (!out || *out || bytes > RW_MAX_CORPUS_BYTES) return RW_ARGUMENT;
    const char *locale = setlocale(LC_ALL, NULL);
    if (!locale || strcmp(locale, "C")) return RW_ARGUMENT;
    rw_workload *w = owned_alloc(sizeof(*w));
    if (!w) return RW_MEMORY;
    w->bytes = bytes; w->blocks = bytes ? (bytes + RW_REQUEST_BYTES - 1u) / RW_REQUEST_BYTES : 1u;
    w->storage = bytes + w->blocks;
    w->corpus = owned_alloc(w->storage); w->chunks = owned_alloc(w->blocks * sizeof(*w->chunks));
    if (!w->corpus || !w->chunks) { rw_destroy(&w); return RW_MEMORY; }
    for (size_t i = 0, left = bytes, offset = 0; i < w->blocks; ++i) {
        rw_chunk *c = &w->chunks[i]; c->offset = offset; c->length = left > RW_REQUEST_BYTES ? RW_REQUEST_BYTES : left;
        generate(w, i, seed); left -= c->length; offset += c->length + 1u;
    }
    for (unsigned p = 0; p < RW_PATTERNS; ++p) {
        const char *pattern = patterns[p];
#ifdef RW_TESTING
        if ((int)p == fail_compile) pattern = "[";
#endif
        int error = regcomp(&w->regex[p], pattern, REG_EXTENDED | REG_NEWLINE);
        if (error) { rw_destroy(&w); return RW_LIBRARY; }
        ++w->compiled;
#ifdef RW_TESTING
        ++compiles;
#endif
    }
    *out = w; return RW_OK;
}

static int evaluate(const rw_workload *w, const rw_chunk *c, unsigned p, rw_result *r) {
    const char *text = w->corpus + c->offset; size_t offset = 0;
    r->matches = 0; r->checksum = BASIS;
    if (text[c->length]) return RW_CORRUPT;
    for (;;) {
        regmatch_t matches[5];
        for (unsigned g = 0; g < 5; ++g) matches[g].rm_so = matches[g].rm_eo = -1;
        int error;
#ifdef RW_TESTING
        if ((int)p == fail_execute) error = REG_ESPACE;
        else
#endif
        error = regexec(&w->regex[p], text + offset, 5, matches, offset ? REG_NOTBOL : 0);
        if (error == REG_NOMATCH) return RW_OK;
        if (error) return RW_LIBRARY;
        if (matches[0].rm_eo <= matches[0].rm_so) return RW_CORRUPT;
        ++r->matches;
        for (unsigned g = 0; g < 5; ++g) {
            if (matches[g].rm_so < 0 || matches[g].rm_eo < matches[g].rm_so ||
                (size_t)matches[g].rm_eo > c->length - offset) return RW_CORRUPT;
            size_t begin = offset + (size_t)matches[g].rm_so, end = offset + (size_t)matches[g].rm_eo;
            r->checksum = hash_number(r->checksum, begin); r->checksum = hash_number(r->checksum, end);
            for (size_t i = begin; i < end; ++i) r->checksum = hash_byte(r->checksum, (unsigned char)text[i]);
        }
        offset += (size_t)matches[0].rm_eo;
    }
}

int rw_request(rw_workload *w, rw_result results[RW_PATTERNS]) {
    if (!w || !results || w->compiled != RW_PATTERNS) return RW_ARGUMENT;
    if (w->poisoned) return RW_POISONED;
    if (w->requests == UINT64_MAX) { w->poisoned = 1; return RW_ARGUMENT; }
    rw_chunk *c = &w->chunks[w->requests % w->blocks];
    for (unsigned p = 0; p < RW_PATTERNS; ++p) {
        int error = evaluate(w, c, p, &results[p]);
        if (!error && (results[p].matches != c->expected[p].matches || results[p].checksum != c->expected[p].checksum)) error = RW_CORRUPT;
        if (error) { w->poisoned = 1; return error; }
    }
    for (unsigned p = 0; p < RW_PATTERNS; ++p) {
        w->totals[p].matches += results[p].matches; w->totals[p].checksum += results[p].checksum;
    }
    ++w->requests; return RW_OK;
}

int rw_verify(const rw_workload *w, uint64_t requests) {
    if (!w || w->compiled != RW_PATTERNS) return RW_ARGUMENT;
    if (w->poisoned || w->requests != requests) return RW_CORRUPT;
    rw_result expected[RW_PATTERNS] = {{0, 0}, {0, 0}, {0, 0}};
    for (size_t b = 0; b < w->blocks; ++b) {
        const rw_chunk *c = &w->chunks[b]; const char *text = w->corpus + c->offset;
        if (text[c->length] || hash_text(text, c->length) != c->input_hash) return RW_CORRUPT;
        uint64_t count = requests / w->blocks + (b < requests % w->blocks);
        for (unsigned p = 0; p < RW_PATTERNS; ++p) {
            expected[p].matches += count * c->expected[p].matches;
            expected[p].checksum += count * c->expected[p].checksum;
        }
    }
    for (unsigned p = 0; p < RW_PATTERNS; ++p)
        if (expected[p].matches != w->totals[p].matches || expected[p].checksum != w->totals[p].checksum) return RW_CORRUPT;
    return RW_OK;
}

int rw_memory_usage(const rw_workload *w, rw_memory *out) {
    if (!w || !out) return RW_ARGUMENT;
    *out = (rw_memory){w->bytes, w->blocks, w->storage, sizeof(*w) + w->blocks * sizeof(*w->chunks)};
    return RW_OK;
}
const char *rw_pattern(unsigned p) { return p < RW_PATTERNS ? patterns[p] : NULL; }
const char *rw_block(const rw_workload *w, size_t index, size_t *length) {
    if (!w || !length || index >= w->blocks) return NULL;
    *length = w->chunks[index].length; return w->corpus + w->chunks[index].offset;
}
