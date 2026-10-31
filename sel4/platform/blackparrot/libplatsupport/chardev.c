/* SPDX-License-Identifier: BSD-2-Clause */

#include "../../chardev.h"

struct ps_chardevice *
ps_cdev_init(enum chardev_id id, const ps_io_ops_t *ops, struct ps_chardevice *device)
{
    (void)id;
    (void)ops;
    (void)device;
    return NULL;
}
