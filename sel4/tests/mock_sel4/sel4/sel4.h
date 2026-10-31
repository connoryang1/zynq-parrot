#ifndef MOCK_SEL4_H
#define MOCK_SEL4_H

#include <stdint.h>

typedef uint64_t seL4_Word;
typedef uint64_t seL4_CPtr;
typedef struct {
    seL4_Word words[1];
} seL4_MessageInfo_t;

enum {
    seL4_NoError = 0,
    seL4_InvalidArgument,
    seL4_InvalidCapability,
    seL4_IllegalOperation,
    seL4_RangeError,
    seL4_AlignmentError,
    seL4_FailedLookup,
    seL4_TruncatedMessage,
    seL4_DeleteFirst,
    seL4_RevokeFirst,
    seL4_NotEnoughMemory,
};

extern seL4_Word mock_sel4_mrs[8];
extern seL4_CPtr mock_sel4_caps[4];

static inline seL4_MessageInfo_t seL4_MessageInfo_new(
    seL4_Word label, seL4_Word caps_unwrapped, seL4_Word extra_caps,
    seL4_Word length)
{
    (void)caps_unwrapped;
    return (seL4_MessageInfo_t) {
        .words = {(label << 16) | (extra_caps << 8) | length},
    };
}

static inline seL4_Word seL4_MessageInfo_get_label(seL4_MessageInfo_t info)
{
    return info.words[0] >> 16;
}

static inline void seL4_SetMR(int index, seL4_Word value)
{
    mock_sel4_mrs[index] = value;
}

static inline seL4_Word seL4_GetMR(int index)
{
    return mock_sel4_mrs[index];
}

static inline void seL4_SetCap(int index, seL4_CPtr value)
{
    mock_sel4_caps[index] = value;
}

seL4_MessageInfo_t seL4_Call(seL4_CPtr endpoint, seL4_MessageInfo_t info);

#endif
