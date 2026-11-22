/* Check the interrupted PC before a reseeded resident U target retires.
 * A latched CLINT MSIP, armed with bounded pending-bit readback, makes this
 * a controlled trap-PC invariant test. It does not recreate Linux trap state
 * or establish the cause of the observed Linux old-park return.
 */
#define BP_RESEED_IRQ_TEST 1
#include "mt_resident_reseed_fetch_test.c"
