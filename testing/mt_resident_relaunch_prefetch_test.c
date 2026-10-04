/* Enable the detached-prefetch variant of the resident relaunch regression. */
#define BP_RELAUNCH_PREFETCH 1
#define BP_RELAUNCH_ROUNDS 256
#include "mt_resident_relaunch_register_test.c"
