/**
 * mt_ctxtsw_context_cache_cooperative_image.c
 *
 * Software-only context-image format test for the future resident-miss context
 * cache. This does not switch to a nonresident logical context. It proves that
 * the reserved backing image layout can hold independent logical context state
 * before RTL save/restore starts consuming the format.
 */

#include <stdint.h>
#include "bp_utils.h"
#include "mt_context_image.h"

#if BP_NUM_CONTEXTS < 4
#error "mt_ctxtsw_context_cache_cooperative_image requires BP_NUM_CONTEXTS >= 4"
#endif

static volatile mt_context_image_t context_images[BP_NUM_CONTEXTS]
  __attribute__((aligned(MT_CONTEXT_IMAGE_STRIDE_BYTES)));

static void fail_word(uint64_t ctx, uint64_t word, uint64_t got, uint64_t expected) {
  bp_print_string("[BSG-FAIL] ctx=");
  bp_hprint_uint64(ctx);
  bp_print_string(" word=");
  bp_hprint_uint64(word);
  bp_print_string(" got=");
  bp_hprint_uint64(got);
  bp_print_string(" expected=");
  bp_hprint_uint64(expected);
  bp_print_string("\n");
  bp_finish(1);
}

static void check_image(uint64_t logical_id, uint64_t npc) {
  volatile mt_context_image_t *image = &context_images[logical_id];

  for (uint64_t word = 0; word < MT_CONTEXT_IMAGE_WORDS; word++) {
    uint64_t got = image->word[word];
    uint64_t expected = mt_context_image_expected_word(logical_id, word, npc);
    if (got != expected)
      fail_word(logical_id, word, got, expected);
  }
}

int main(void) {
  bp_print_string("=== Context Cache Cooperative Image Test ===\n");
  bp_print_string("Contexts: ");
  bp_hprint_uint64(BP_NUM_CONTEXTS);
  bp_print_string("\nResident threads: ");
  bp_hprint_uint64(BP_NUM_THREADS);
  bp_print_string("\nImage stride bytes: ");
  bp_hprint_uint64(MT_CONTEXT_IMAGE_STRIDE_BYTES);
  bp_print_string("\n");

  uintptr_t base = (uintptr_t)&context_images[0];
  uintptr_t next = (uintptr_t)&context_images[1];
  if ((next - base) != MT_CONTEXT_IMAGE_STRIDE_BYTES) {
    bp_print_string("[BSG-FAIL] unexpected context image stride\n");
    bp_finish(1);
  }

  for (uint64_t ctx = 0; ctx < 4; ctx++) {
    uint64_t npc = 0x80001000ULL + (ctx * 0x100ULL);
    mt_context_image_init(&context_images[ctx], ctx, npc);
  }

  for (uint64_t ctx = 0; ctx < 4; ctx++) {
    uint64_t npc = 0x80001000ULL + (ctx * 0x100ULL);
    check_image(ctx, npc);
  }

  context_images[2].word[MT_CONTEXT_IMAGE_GPR_BASE_WORD + 5] = 0x2222000000000005ULL;
  context_images[3].word[MT_CONTEXT_IMAGE_GPR_BASE_WORD + 5] = 0x3333000000000005ULL;

  if (context_images[2].word[MT_CONTEXT_IMAGE_GPR_BASE_WORD + 5] != 0x2222000000000005ULL)
    fail_word(2, MT_CONTEXT_IMAGE_GPR_BASE_WORD + 5,
              context_images[2].word[MT_CONTEXT_IMAGE_GPR_BASE_WORD + 5],
              0x2222000000000005ULL);

  if (context_images[3].word[MT_CONTEXT_IMAGE_GPR_BASE_WORD + 5] != 0x3333000000000005ULL)
    fail_word(3, MT_CONTEXT_IMAGE_GPR_BASE_WORD + 5,
              context_images[3].word[MT_CONTEXT_IMAGE_GPR_BASE_WORD + 5],
              0x3333000000000005ULL);

  if (context_images[2].word[MT_CONTEXT_IMAGE_GPR_BASE_WORD + 5]
      == context_images[3].word[MT_CONTEXT_IMAGE_GPR_BASE_WORD + 5]) {
    bp_print_string("[BSG-FAIL] logical image slots alias each other\n");
    bp_finish(1);
  }

  bp_print_string("[BSG-PASS] cooperative context image layout verified\n");
  bp_finish(0);
  return 0;
}
