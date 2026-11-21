#define _POSIX_C_SOURCE 200809L
#include <inttypes.h>
#include <stdio.h>
#include "retained29_regex_workload.h"

static int number(const char *text, uint64_t *out)
{
	char *end;
	if (!*text || *text == '-') return -1;
	errno = 0; *out = strtoull(text, &end, 0);
	return errno || *end ? -1 : 0;
}

int main(int argc, char **argv)
{
	uint64_t kib, seed, requests;
	if ((argc != 4 && argc != 5) || number(argv[1], &kib) || number(argv[2], &seed) ||
			number(argv[3], &requests) || kib > 128 || requests > 1000 ||
			(argc == 5 && strcmp(argv[4], "--dump"))) return 2;
	struct retained29_regex_workload w;
	if (retained29_regex_init(&w, (unsigned)kib, seed)) return 3;
	printf("CORPUS bytes=%zu records=%zu seed=%" PRIu64 " metadata=%zu hash=%016" PRIx64 "\n",
			w.bytes, w.records, seed, w.records * sizeof(*w.record), w.corpus_hash);
	if (argc == 5)
		for (size_t n = 0; n < w.records; ++n) {
			const struct retained29_regex_record *r = &w.record[n];
			printf("ROW %zu %u %u ", n, r->offset, (unsigned)r->length);
			for (unsigned b = 0; b < r->length; ++b)
				printf("%02x", (unsigned char)w.corpus[r->offset + b]);
			putchar('\n');
		}
	uint64_t total = 0;
	for (uint64_t n = 0; n < requests; ++n) {
		uint64_t result = retained29_regex_run(&w);
		total += result;
		printf("REQUEST %" PRIu64 " %016" PRIx64 " calls=%" PRIu64 " positive=%" PRIu64 " negative=%" PRIu64 "\n",
				n, result, w.calls, w.positive_calls, w.negative_calls);
	}
	int ok = retained29_regex_check_total(&w, total);
	retained29_regex_free(&w);
	if (!ok) return 4;
	puts("RETAINED29_REGEX_FUNCTIONAL_PASS");
	return 0;
}
