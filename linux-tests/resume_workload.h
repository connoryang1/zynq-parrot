/* Private post-resume work, independent of the replay transport and timer.
 * Checks derive expected values from the generator, never by rereading data.
 * Call check_total outside timing; run() contains only request processing.
 */
#ifndef RESUME_WORKLOAD_H
#define RESUME_WORKLOAD_H

#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum resume_workload_kind { resume_scan, resume_lookup, resume_parse, resume_chase };

struct resume_lookup_slot { uint64_t key, value; };
struct resume_chase_node { uint64_t next, value; unsigned char padding[48]; };

struct resume_workload {
	enum resume_workload_kind kind;
	unsigned char *data;
	size_t bytes, count, records, cursor;
	uint64_t seed, runs, constant_expected;
};

static inline uint64_t resume_workload_mix(uint64_t x)
{
	x ^= x >> 30;
	x *= UINT64_C(0xbf58476d1ce4e5b9);
	x ^= x >> 27;
	x *= UINT64_C(0x94d049bb133111eb);
	return x ^ (x >> 31);
}

/* A different request batch each epoch; one eighth deliberately misses. */
static inline uint64_t resume_workload_key(const struct resume_workload *w,
		uint64_t epoch, unsigned query)
{
	uint64_t random = resume_workload_mix(w->seed + epoch * 64 + query);
	return 1 + random % w->records + ((query & 7) == 7 ? w->records : 0);
}

static inline void resume_workload_free(struct resume_workload *w)
{
	free(w->data);
	memset(w, 0, sizeof(*w));
}

static inline int resume_workload_init(struct resume_workload *w,
		const char *mode, unsigned kib, uint64_t seed)
{
	size_t i;
	memset(w, 0, sizeof(*w));
	if (!mode) {
		errno = EINVAL;
		return -1;
	}
	if (!strcmp(mode, "scan")) w->kind = resume_scan;
	else if (!strcmp(mode, "lookup")) w->kind = resume_lookup;
	else if (!strcmp(mode, "parse")) w->kind = resume_parse;
	else if (!strcmp(mode, "chase")) w->kind = resume_chase;
	else {
		errno = EINVAL;
		return -1;
	}
	if ((uint64_t)kib * 1024 > SIZE_MAX) {
		errno = EOVERFLOW;
		return -1;
	}
	w->bytes = (size_t)kib * 1024;
	w->seed = seed;
	if (!w->bytes) return 0;
	w->data = calloc(1, w->bytes);
	if (!w->data) return -1;
	if (w->kind == resume_scan) {
		for (i = 0; i < w->bytes; i += 64) {
			unsigned char value = (unsigned char)(seed + i / 64);
			w->data[i] = value;
			w->constant_expected += value;
		}
	} else if (w->kind == resume_lookup) {
		struct resume_lookup_slot *slots = (void *)w->data;
		w->count = w->bytes / sizeof(*slots);
		w->records = w->count / 2;
		for (i = 1; i <= w->records; ++i) {
			size_t slot = resume_workload_mix(i) % w->count;
			while (slots[slot].key) slot = (slot + 1) % w->count;
			slots[slot].key = i;
			slots[slot].value = resume_workload_mix(seed ^ i);
		}
	} else if (w->kind == resume_parse) {
		/* Compact text records: decimal key, colon, variable payload, newline.
		 * Unlike a fixed-stride load loop, field lengths control the next read.
		 */
		size_t offset = 0;
		for (i = 0; ; ++i) {
			uint64_t random = resume_workload_mix(seed + i);
			unsigned key = 1 + random % 1000000;
			unsigned length = 16 + (random >> 24) % 97;
			char reverse[10];
			unsigned digits = 0, value = key, j;
			do { reverse[digits++] = '0' + value % 10; value /= 10; } while (value);
			if (offset + digits + length + 3 > w->bytes) break;
			w->constant_expected += key;
			for (j = digits; j; --j) w->data[offset++] = reverse[j - 1];
			w->data[offset++] = ':';
			for (j = 0; j < length; ++j) {
				unsigned char c = 'a' + (random + j * 7) % 26;
				w->data[offset++] = c;
				w->constant_expected += c;
			}
			w->data[offset++] = '\n';
			++w->records;
		}
		w->count = offset;
	} else {
		struct resume_chase_node *nodes = (void *)w->data;
		size_t *order;
		w->count = w->bytes / sizeof(*nodes);
		order = malloc(w->count * sizeof(*order));
		if (!order) { resume_workload_free(w); return -1; }
		for (i = 0; i < w->count; ++i) order[i] = i;
		for (i = w->count - 1; i; --i) {
			size_t j = resume_workload_mix(seed + i) % (i + 1);
			size_t tmp = order[i]; order[i] = order[j]; order[j] = tmp;
		}
		for (i = 0; i < w->count; ++i) {
			nodes[order[i]].next = order[(i + 1) % w->count];
			nodes[order[i]].value = resume_workload_mix(seed ^ i);
		}
		w->cursor = order[0];
		free(order);
	}
	return 0;
}

static inline uint64_t resume_workload_run(struct resume_workload *w)
{
	uint64_t result = 0, epoch = w->runs++;
	size_t i;
	if (!w->bytes) return 0;
	if (w->kind == resume_scan) {
		volatile unsigned char *data = w->data;
		for (i = 0; i < w->bytes; i += 64) result += data[i];
	} else if (w->kind == resume_lookup) {
		volatile struct resume_lookup_slot *slots = (void *)w->data;
		for (i = 0; i < 64; ++i) {
			uint64_t key = resume_workload_key(w, epoch, i);
			size_t slot = resume_workload_mix(key) % w->count, probes;
			for (probes = 0; probes < w->count; ++probes) {
				uint64_t found = slots[slot].key;
				if (!found) break;
				if (found == key) { result += slots[slot].value; break; }
				slot = (slot + 1) % w->count;
			}
		}
	} else if (w->kind == resume_parse) {
		volatile unsigned char *data = w->data;
		i = 0;
		while (i < w->count) {
			uint64_t key = 0;
			while (i < w->count && data[i] >= '0' && data[i] <= '9')
				key = key * 10 + data[i++] - '0';
			if (i == w->count || data[i++] != ':') return UINT64_MAX;
			result += key;
			while (i < w->count && data[i] != '\n') result += data[i++];
			if (i == w->count) return UINT64_MAX;
			++i;
		}
	} else {
		volatile struct resume_chase_node *nodes = (void *)w->data;
		size_t steps = w->count < 64 ? w->count : 64;
		for (i = 0; i < steps; ++i) {
			if (w->cursor >= w->count) return UINT64_MAX;
			result += nodes[w->cursor].value;
			w->cursor = nodes[w->cursor].next;
		}
	}
	return result;
}

static inline uint64_t resume_workload_expected(const struct resume_workload *w,
		uint64_t epoch)
{
	uint64_t expected = 0;
	size_t i;
	if (!w->bytes) return 0;
	if (w->kind == resume_scan || w->kind == resume_parse)
		return w->constant_expected;
	if (w->kind == resume_lookup) {
		for (i = 0; i < 64; ++i) {
			uint64_t key = resume_workload_key(w, epoch, i);
			if (key <= w->records) expected += resume_workload_mix(w->seed ^ key);
		}
	} else {
		size_t steps = w->count < 64 ? w->count : 64;
		for (i = 0; i < steps; ++i)
			expected += resume_workload_mix(w->seed ^ ((epoch * steps + i) % w->count));
	}
	return expected;
}

static inline int resume_workload_check(const struct resume_workload *w,
		uint64_t observed)
{
	return w->runs && observed == resume_workload_expected(w, w->runs - 1);
}

static inline int resume_workload_check_total(const struct resume_workload *w,
		uint64_t observed)
{
	uint64_t expected = 0, epoch;
	if (w->kind == resume_scan || w->kind == resume_parse)
		expected = w->constant_expected * w->runs;
	else
		for (epoch = 0; epoch < w->runs; ++epoch)
			expected += resume_workload_expected(w, epoch);
	return observed == expected;
}

#endif
