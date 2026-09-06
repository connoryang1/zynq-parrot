/*
 * Exercise the nonresident U-mode handoff with Sv39 instruction translation.
 * The shared handoff gate runs through a low userspace alias so this variant
 * catches stale translated frontend work that translation-off tests cannot.
 */

#define BP_ENABLE_SV39 1
#include "mt_umode_nonresident_handoff_test.c"
