#define _POSIX_C_SOURCE 200809L
#include <features.h>
#include <stddef.h>
#include <regex.h>
#if !defined(__riscv) || __riscv_xlen != 64
#error This probe must use the actual RV64 cross headers
#endif
_Static_assert(__GLIBC__ == 2 && __GLIBC_MINOR__ == 37, "wrong glibc headers");
_Static_assert(sizeof(void *) == 8, "wrong pointer ABI");
_Static_assert(sizeof(regex_t) == 64, "unexpected regex_t ABI");
_Static_assert(offsetof(regex_t, re_nsub) == 48, "unexpected regex capture-count offset");
_Static_assert(sizeof(regoff_t) == 4 && sizeof(regmatch_t) == 8, "large-offset ABI is forbidden");
_Static_assert(REG_EXTENDED == 1 && REG_NEWLINE == 4 && REG_NOTBOL == 1, "wrong regex flag ABI");
const unsigned long regex_abi_values[] = {__GLIBC__, __GLIBC_MINOR__, sizeof(regex_t),
    offsetof(regex_t, re_nsub), sizeof(regoff_t), sizeof(regmatch_t), sizeof(void *)};
