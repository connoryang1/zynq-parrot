#include <stdlib.h>

/* Keep Vivado's process-local preload from leaking into synthesis helpers. */
__attribute__((constructor)) static void clear_preload_for_children(void)
{
  unsetenv("LD_PRELOAD");
}
