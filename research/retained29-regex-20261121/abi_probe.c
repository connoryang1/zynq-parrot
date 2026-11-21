#define _POSIX_C_SOURCE 200809L
#include <features.h>
#include <stddef.h>
#include "retained29_regex_workload.h"
#if !defined(__riscv) || __riscv_xlen != 64
#error Actual RV64 headers required
#endif
_Static_assert(__GLIBC__ == 2 && __GLIBC_MINOR__ == 37, "wrong glibc headers");
_Static_assert(sizeof(void *) == 8 && sizeof(regex_t) == 64, "wrong public regex ABI");
_Static_assert(offsetof(regex_t, re_nsub) == 48, "wrong subexpression field offset");
_Static_assert(sizeof(regoff_t) == 4 && sizeof(regmatch_t) == 8, "large-offset ABI forbidden");
_Static_assert(REG_EXTENDED == 1 && REG_NEWLINE == 4 && REG_NOTBOL == 1, "wrong public flags");
_Static_assert(sizeof(struct retained29_regex_record) == 16, "unexpected descriptor layout");
const unsigned long retained29_regex_abi[] = {sizeof(regex_t), offsetof(regex_t, re_nsub),
	sizeof(regmatch_t), sizeof(regoff_t), sizeof(struct retained29_regex_record)};
