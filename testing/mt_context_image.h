#ifndef MT_CONTEXT_IMAGE_H
#define MT_CONTEXT_IMAGE_H

#include <stdint.h>

#ifndef BP_NUM_CONTEXTS
#define BP_NUM_CONTEXTS BP_NUM_THREADS
#endif

#define MT_CONTEXT_IMAGE_MAGIC 0x435458494d473031ULL /* "CTXIMG01" */
#define MT_CONTEXT_IMAGE_VERSION 1ULL

enum {
  MT_CONTEXT_IMAGE_STRIDE_BYTES = 512,
  MT_CONTEXT_IMAGE_WORDS = MT_CONTEXT_IMAGE_STRIDE_BYTES / sizeof(uint64_t),

  MT_CONTEXT_IMAGE_MAGIC_WORD = 0,
  MT_CONTEXT_IMAGE_VERSION_WORD = 1,
  MT_CONTEXT_IMAGE_LOGICAL_ID_WORD = 2,
  MT_CONTEXT_IMAGE_VALID_WORD = 3,
  MT_CONTEXT_IMAGE_NPC_WORD = 4,
  MT_CONTEXT_IMAGE_META_WORD = 5,
  MT_CONTEXT_IMAGE_SATP_WORD = 6,
  MT_CONTEXT_IMAGE_GPR_BASE_WORD = 8,
  MT_CONTEXT_IMAGE_GPR_COUNT = 32
};

typedef struct {
  uint64_t word[MT_CONTEXT_IMAGE_WORDS];
} mt_context_image_t;

static inline uint64_t mt_context_image_meta(uint64_t prv, uint64_t translation_en, uint64_t asid) {
  return (prv & 0x3ULL)
         | ((translation_en & 0x1ULL) << 2)
         | ((asid & 0xffffULL) << 16);
}

static inline uint64_t mt_context_image_gpr_value(uint64_t logical_id, uint64_t reg) {
  return 0xc170000000000000ULL | ((logical_id & 0xffULL) << 8) | (reg & 0xffULL);
}

static inline void mt_context_image_clear(volatile mt_context_image_t *image) {
  for (uint64_t i = 0; i < MT_CONTEXT_IMAGE_WORDS; i++)
    image->word[i] = 0;
}

static inline void mt_context_image_init(volatile mt_context_image_t *image, uint64_t logical_id, uint64_t npc) {
  mt_context_image_clear(image);

  image->word[MT_CONTEXT_IMAGE_MAGIC_WORD] = MT_CONTEXT_IMAGE_MAGIC;
  image->word[MT_CONTEXT_IMAGE_VERSION_WORD] = MT_CONTEXT_IMAGE_VERSION;
  image->word[MT_CONTEXT_IMAGE_LOGICAL_ID_WORD] = logical_id;
  image->word[MT_CONTEXT_IMAGE_VALID_WORD] = 1;
  image->word[MT_CONTEXT_IMAGE_NPC_WORD] = npc;
  image->word[MT_CONTEXT_IMAGE_META_WORD] = mt_context_image_meta(3, 0, logical_id);
  image->word[MT_CONTEXT_IMAGE_SATP_WORD] = 0;

  image->word[MT_CONTEXT_IMAGE_GPR_BASE_WORD] = 0;
  for (uint64_t reg = 1; reg < MT_CONTEXT_IMAGE_GPR_COUNT; reg++)
    image->word[MT_CONTEXT_IMAGE_GPR_BASE_WORD + reg] = mt_context_image_gpr_value(logical_id, reg);
}

static inline uint64_t mt_context_image_expected_word(uint64_t logical_id, uint64_t word, uint64_t npc) {
  if (word == MT_CONTEXT_IMAGE_MAGIC_WORD)
    return MT_CONTEXT_IMAGE_MAGIC;
  if (word == MT_CONTEXT_IMAGE_VERSION_WORD)
    return MT_CONTEXT_IMAGE_VERSION;
  if (word == MT_CONTEXT_IMAGE_LOGICAL_ID_WORD)
    return logical_id;
  if (word == MT_CONTEXT_IMAGE_VALID_WORD)
    return 1;
  if (word == MT_CONTEXT_IMAGE_NPC_WORD)
    return npc;
  if (word == MT_CONTEXT_IMAGE_META_WORD)
    return mt_context_image_meta(3, 0, logical_id);
  if (word == MT_CONTEXT_IMAGE_SATP_WORD)
    return 0;
  if ((word >= MT_CONTEXT_IMAGE_GPR_BASE_WORD)
      && (word < MT_CONTEXT_IMAGE_GPR_BASE_WORD + MT_CONTEXT_IMAGE_GPR_COUNT)) {
    uint64_t reg = word - MT_CONTEXT_IMAGE_GPR_BASE_WORD;
    return reg == 0 ? 0 : mt_context_image_gpr_value(logical_id, reg);
  }

  return 0;
}

#endif /* MT_CONTEXT_IMAGE_H */
