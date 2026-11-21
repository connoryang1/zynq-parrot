
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include "resume_workload.h"

static int fault;
static unsigned compress_calls, uncompress_calls;
static uLong request_bytes;
int __real_compress2(Bytef *, uLongf *, const Bytef *, uLong, int);
int __real_uncompress(Bytef *, uLongf *, const Bytef *, uLong);
int __wrap_compress2(Bytef *out, uLongf *out_bytes,
                     const Bytef *in, uLong in_bytes, int level)
{
    ++compress_calls;
    request_bytes = in_bytes;
    assert(level == Z_DEFAULT_COMPRESSION);
    if (fault == 1) return Z_STREAM_ERROR;
    if (fault == 2) return Z_MEM_ERROR;
    int result = __real_compress2(out, out_bytes, in, in_bytes, level);
    if (fault == 3 && result == Z_OK) out[0] ^= 0xff;
    return result;
}
int __wrap_uncompress(Bytef *out, uLongf *out_bytes,
                      const Bytef *in, uLong in_bytes)
{
    ++uncompress_calls;
    if (fault == 4) return Z_DATA_ERROR;
    int result = __real_uncompress(out, out_bytes, in, in_bytes);
    if (result == Z_OK && fault == 5) --*out_bytes;
    if (result == Z_OK && fault == 6) out[0] ^= 1;
    return result;
}
int main(int argc, char **argv)
{
    struct resume_workload w;
    uint64_t seed, total = 0, ideal_total = 0;
    unsigned kib, epochs;
    const char *action;
    if (argc != 5) return 2;
    kib = strtoul(argv[1], NULL, 0);
    seed = strtoull(argv[2], NULL, 0);
    action = argv[3];
    epochs = strtoul(argv[4], NULL, 0);
    if (resume_workload_init(&w, "deflate", kib, seed)) return 3;
    assert(resume_workload_check_total(&w, 0));
    printf("META %zu %zu %zu %zu\n", w.bytes, w.count,
           w.zlib_blocks, w.zlib_compressed_capacity);
    if (!strcmp(action, "input-corrupt") || !strcmp(action, "last-corrupt")) {
        if (!w.bytes) return 4;
        w.data[!strcmp(action, "last-corrupt") ? w.bytes - 1 : 0] ^= 1;
    } else if (!strcmp(action, "compress-error")) fault = 1;
    else if (!strcmp(action, "memory-error")) fault = 2;
    else if (!strcmp(action, "compressed-corrupt")) fault = 3;
    else if (!strcmp(action, "uncompress-error")) fault = 4;
    else if (!strcmp(action, "short-output")) fault = 5;
    else if (!strcmp(action, "output-corrupt")) fault = 6;
    else assert(!strcmp(action, "run"));
    for (unsigned epoch = 0; epoch < epochs; ++epoch) {
        uint64_t expected = resume_workload_expected(&w, epoch);
        uint64_t result = resume_workload_run(&w);
        ideal_total += expected;
        total += result;
        if (fault && fault != 6) {
            assert(result == UINT64_MAX && w.zlib_error != Z_OK);
            assert(!resume_workload_check(&w, result));
            /* Even a forged matching total must fail after a library error. */
            assert(!resume_workload_check_total(&w, ideal_total));
        } else {
            int damaged = fault == 6 ||
                (!strcmp(action, "input-corrupt") && epoch % w.zlib_blocks == 0) ||
                (!strcmp(action, "last-corrupt") &&
                 epoch % w.zlib_blocks == w.zlib_blocks - 1);
            assert(resume_workload_check(&w, result) == !damaged);
            assert(w.zlib_error == Z_OK);
        }
        printf("ROW %u %lu %" PRIu64 "\n", epoch, request_bytes, result);
    }
    if (!strcmp(action, "run")) {
        assert(resume_workload_check_total(&w, total));
        assert(!resume_workload_check_total(&w, total + 1));
        assert(compress_calls == (w.bytes ? epochs : 0));
        assert(uncompress_calls == compress_calls);
        if (w.bytes) assert(w.cursor == epochs % w.zlib_blocks);
    } else assert(!resume_workload_check_total(&w, total));
    printf("TOTAL %" PRIu64 "\n", total);
    resume_workload_free(&w);
    assert(!w.data && !w.bytes && !w.runs && !w.zlib_compressed
           && !w.zlib_output && !w.zlib_expected_crc && !w.zlib_blocks);
    return 0;
}
