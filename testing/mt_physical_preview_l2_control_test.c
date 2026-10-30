/* Build the physical-preview CSR gate with target hints disabled.
 * The same addresses, probe hint, PMA checks, and four demand loads remain.
 * Comparing L2 DMA target fills with the hinted gate tests demand residency.
 */
#define BP_NO_TARGET_PHYSICAL_PREVIEW 1
#include "mt_physical_preview_csr_test.c"
