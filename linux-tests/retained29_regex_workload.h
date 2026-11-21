/* Real POSIX log filtering; no clocks, scheduler, hints or address geometry.
 * Future WHOLE must include init, final checks and free. Corpus bytes exclude
 * descriptors and libc's opaque compiled/lazy matching allocations.
 */
#ifndef RETAINED29_REGEX_WORKLOAD_H
#define RETAINED29_REGEX_WORKLOAD_H

#include <errno.h>
#include <locale.h>
#include <regex.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define RETAINED29_REGEX_PATTERNS 3U
#define RETAINED29_REGEX_QUERIES 64U
#define RETAINED29_REGEX_BASIS UINT64_C(14695981039346656037)
#define RETAINED29_REGEX_PRIME UINT64_C(1099511628211)

struct retained29_regex_record {
	uint32_t offset;
	uint16_t length;
	uint8_t matches, reserved;
	uint64_t capture_hash;
};

struct retained29_regex_workload {
	regex_t regex[RETAINED29_REGEX_PATTERNS];
	char *corpus;
	struct retained29_regex_record *record;
	size_t bytes, records;
	uint64_t seed, runs, calls, positive_calls, negative_calls;
	uint64_t corpus_hash, metadata_hash;
	unsigned compiled, compile_calls;
	int error;
};

static inline const char *retained29_regex_pattern(unsigned p)
{
	static const char *const patterns[RETAINED29_REGEX_PATTERNS] = {
		"^id=([0-9]{1,6}) user=([a-z]{3,8}) status=(ok|warn|fail) bytes=([0-9]{1,5})$",
		"^id=([0-9]{1,6}) user=([a-z]{3,8}) status=(warn|fail) bytes=([0-9]{1,5})$",
		"^id=([0-9]{1,6}) user=([a-z]{3,8}) status=(fail) bytes=([0-9]{1,5})$"
	};
	return p < RETAINED29_REGEX_PATTERNS ? patterns[p] : NULL;
}

static inline uint64_t retained29_regex_mix(uint64_t x)
{
	x ^= x >> 30; x *= UINT64_C(0xbf58476d1ce4e5b9);
	x ^= x >> 27; x *= UINT64_C(0x94d049bb133111eb);
	return x ^ (x >> 31);
}

static inline uint64_t retained29_regex_byte(uint64_t h, unsigned char c)
{
	return (h ^ c) * RETAINED29_REGEX_PRIME;
}

static inline uint64_t retained29_regex_number(uint64_t h, uint64_t x)
{
	for (unsigned n = 0; n < 8; ++n) {
		h = retained29_regex_byte(h, (unsigned char)x); x >>= 8;
	}
	return h;
}

static inline uint64_t retained29_regex_hash(const void *data, size_t bytes)
{
	const unsigned char *text = data;
	uint64_t h = RETAINED29_REGEX_BASIS;
	for (size_t n = 0; n < bytes; ++n) h = retained29_regex_byte(h, text[n]);
	return h;
}

static inline void retained29_regex_append(char *text, size_t *n, const char *s)
{
	size_t bytes = strlen(s);
	memcpy(text + *n, s, bytes); *n += bytes;
}

static inline void retained29_regex_decimal(char *text, size_t *n, uint32_t x)
{
	char digits[10]; unsigned count = 0;
	do { digits[count++] = (char)('0' + x % 10U); x /= 10U; } while (x);
	while (count) text[(*n)++] = digits[--count];
}

/* Maximum row <80 bytes. Oracle uses generator-known field boundaries and
 * classes, never regexec or prior observed results. Packed rows are NUL-ended.
 */
static inline void retained29_regex_generate(uint64_t seed, size_t ordinal,
		char text[128], struct retained29_regex_record *record)
{
	uint64_t random = retained29_regex_mix(seed ^ ordinal);
	unsigned kind = ordinal % 5, userlen = 3 + (unsigned)(random >> 8) % 6;
	size_t n = 0, begin[5] = {0}, end[5] = {0};
	memset(record, 0, sizeof(*record));
	if (kind == 3) {
		retained29_regex_append(text, &n, "note=ignored sequence=");
		retained29_regex_decimal(text, &n, (uint32_t)(random % 1000000));
	} else {
		retained29_regex_append(text, &n, "id="); begin[1] = n;
		retained29_regex_decimal(text, &n, (uint32_t)(random % 1000000)); end[1] = n;
		retained29_regex_append(text, &n, " user="); begin[2] = n;
		for (unsigned k = 0; k < userlen; ++k)
			text[n++] = (char)('a' + (random + k * 7U) % 26);
		end[2] = n;
		retained29_regex_append(text, &n, " status="); begin[3] = n;
		retained29_regex_append(text, &n, kind == 1 ? "warn" : kind == 2 ? "fail" : "ok"); end[3] = n;
		retained29_regex_append(text, &n, " bytes="); begin[4] = n;
		retained29_regex_decimal(text, &n, (uint32_t)((random >> 5) % 100000)); end[4] = n;
		if (kind == 4) retained29_regex_append(text, &n, " extra=ignored");
	}
	text[n] = 0; end[0] = n;
	record->length = (uint16_t)n;
	record->matches = kind < 3 ? (uint8_t)((1U << (kind + 1)) - 1) : 0;
	record->capture_hash = RETAINED29_REGEX_BASIS;
	if (record->matches)
		for (unsigned g = 0; g < 5; ++g) {
			record->capture_hash = retained29_regex_number(record->capture_hash, begin[g]);
			record->capture_hash = retained29_regex_number(record->capture_hash, end[g]);
			for (size_t k = begin[g]; k < end[g]; ++k)
				record->capture_hash = retained29_regex_byte(record->capture_hash, (unsigned char)text[k]);
		}
}

static inline void retained29_regex_free(struct retained29_regex_workload *w)
{
	if (!w) return;
	while (w->compiled) regfree(&w->regex[--w->compiled]);
	free(w->record); free(w->corpus);
	memset(w, 0, sizeof(*w));
}

/* Use fresh or freed caller storage; failure leaves it safe to free. The C
 * locale must already be selected; no process-global locale is changed here.
 */
static inline int retained29_regex_init(struct retained29_regex_workload *w,
		unsigned kib, uint64_t seed)
{
	char text[128]; struct retained29_regex_record row;
	size_t used = 0, count = 0;
	if (!w) { errno = EINVAL; return -1; }
	memset(w, 0, sizeof(*w));
	const char *locale = setlocale(LC_ALL, NULL);
	if ((kib != 32 && kib != 128) || !locale || strcmp(locale, "C")) {
		errno = EINVAL; return -1;
	}
	w->bytes = (size_t)kib * 1024; w->seed = seed;
	/* Discover the exact descriptor count before allocating it. Both passes,
	 * pattern compilation and lazy library allocation remain real whole costs.
	 */
	for (;;) {
		retained29_regex_generate(seed, count, text, &row);
		if ((size_t)row.length + 1 > w->bytes - used) break;
		used += row.length + 1; ++count;
	}
	w->records = count;
	w->corpus = malloc(w->bytes);
	w->record = calloc(count, sizeof(*w->record));
	if (!w->corpus || !w->record) {
		retained29_regex_free(w); errno = ENOMEM; return -1;
	}
	used = 0;
	for (size_t n = 0; n < count; ++n) {
		retained29_regex_generate(seed, n, text, &w->record[n]);
		w->record[n].offset = (uint32_t)used;
		memcpy(w->corpus + used, text, w->record[n].length + 1);
		used += w->record[n].length + 1;
	}
	memset(w->corpus + used, '#', w->bytes - used);
	w->corpus_hash = retained29_regex_hash(w->corpus, w->bytes);
	w->metadata_hash = retained29_regex_hash(w->record, count * sizeof(*w->record));
	for (unsigned p = 0; p < RETAINED29_REGEX_PATTERNS; ++p) {
		++w->compile_calls;
		if (regcomp(&w->regex[p], retained29_regex_pattern(p), REG_EXTENDED)) {
			retained29_regex_free(w); errno = EIO; return -1;
		}
		++w->compiled;
		if (w->regex[p].re_nsub != 4) {
			retained29_regex_free(w); errno = EIO; return -1;
		}
	}
	return 0;
}

static inline uint64_t retained29_regex_result(uint64_t random, unsigned pattern,
		int matched, uint64_t capture)
{
	return retained29_regex_mix(random ^ ((uint64_t)pattern << 61)
			^ (matched ? capture : UINT64_C(0x6e6f6d6174636821)));
}

static inline uint64_t retained29_regex_run(struct retained29_regex_workload *w)
{
	uint64_t total = 0;
	if (!w || w->compiled != RETAINED29_REGEX_PATTERNS || w->error ||
			!w->records || w->runs >= UINT64_MAX / RETAINED29_REGEX_QUERIES) {
		if (w) w->error = EINVAL;
		errno = EINVAL; return UINT64_MAX;
	}
	for (unsigned query = 0; query < RETAINED29_REGEX_QUERIES; ++query) {
		uint64_t random = retained29_regex_mix(w->seed + w->runs * 64 + query);
		unsigned p = (unsigned)((random >> 32) % RETAINED29_REGEX_PATTERNS);
		const struct retained29_regex_record *row = &w->record[random % w->records];
		regmatch_t match[5];
		uint64_t digest = RETAINED29_REGEX_BASIS;
		if (row->offset >= w->bytes || row->length >= w->bytes - row->offset ||
				w->corpus[row->offset + row->length]) goto corrupt;
		const char *text = w->corpus + row->offset;
		++w->calls;
		int error = regexec(&w->regex[p], text, 5, match, 0);
		if (error != 0 && error != REG_NOMATCH) {
			w->error = error; errno = EIO; return UINT64_MAX;
		}
		if (!error) {
			++w->positive_calls;
			if (match[0].rm_so != 0 || match[0].rm_eo != row->length) goto corrupt;
			for (unsigned g = 0; g < 5; ++g) {
				if (match[g].rm_so < 0 || match[g].rm_eo < match[g].rm_so ||
						match[g].rm_eo > row->length) goto corrupt;
				digest = retained29_regex_number(digest, (uint64_t)match[g].rm_so);
				digest = retained29_regex_number(digest, (uint64_t)match[g].rm_eo);
				for (regoff_t k = match[g].rm_so; k < match[g].rm_eo; ++k)
					digest = retained29_regex_byte(digest, (unsigned char)text[k]);
			}
		} else ++w->negative_calls;
		total += retained29_regex_result(random, p, !error, digest);
	}
	++w->runs;
	return total;
corrupt:
	w->error = EIO; errno = EIO; return UINT64_MAX;
}

/* Expected totals use generated field boundaries/classes, never observed
 * regex results. Whole-input/metadata integrity also covers unqueried bytes.
 * These are deterministic integrity checks, not cryptographic guarantees.
 */
static inline int retained29_regex_check_total(const struct retained29_regex_workload *w,
		uint64_t observed)
{
	uint64_t expected = 0;
	if (!w || w->error || w->compiled != RETAINED29_REGEX_PATTERNS ||
			w->compile_calls != RETAINED29_REGEX_PATTERNS || !w->records ||
			w->runs > UINT64_MAX / RETAINED29_REGEX_QUERIES ||
			w->calls != w->runs * RETAINED29_REGEX_QUERIES ||
			w->positive_calls + w->negative_calls != w->calls ||
			retained29_regex_hash(w->corpus, w->bytes) != w->corpus_hash ||
			retained29_regex_hash(w->record, w->records * sizeof(*w->record)) != w->metadata_hash)
		return 0;
	for (uint64_t epoch = 0; epoch < w->runs; ++epoch)
		for (unsigned query = 0; query < RETAINED29_REGEX_QUERIES; ++query) {
			uint64_t random = retained29_regex_mix(w->seed + epoch * 64 + query);
			unsigned p = (unsigned)((random >> 32) % RETAINED29_REGEX_PATTERNS);
			const struct retained29_regex_record *row = &w->record[random % w->records];
			expected += retained29_regex_result(random, p, !!(row->matches & (1U << p)), row->capture_hash);
		}
	return expected == observed;
}

#endif
