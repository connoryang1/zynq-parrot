/*
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * Copyright (c) 2019 Western Digital Corporation or its affiliates.
 */

#include <sbi/riscv_asm.h>
#include <sbi/riscv_encoding.h>
#include <sbi/sbi_const.h>
#include <sbi/sbi_platform.h>
#include <sbi/sbi_system.h>
#include <sbi/sbi_console.h>
#include <sbi/sbi_ipi.h>
#include <sbi/sbi_timer.h>

/*
 * Include these files as needed.
 * See objects.mk PLATFORM_xxx configuration parameters.
 */
#include <sbi_utils/fdt/fdt_helper.h>
#include <sbi_utils/fdt/fdt_fixup.h>
#include <sbi_utils/ipi/aclint_mswi.h>
#include <sbi_utils/timer/aclint_mtimer.h>

#define PLATFORM_FIRST_HARTID 0

#define PLATFORM_HOST_BASE   (0x100000)
#define PLATFORM_CFG_BASE    (0x200000)
#define PLATFORM_CLINT_BASE  (0x300000)
#define PLATFORM_CACHE_BASE  (0x400000)

#define PLATFORM_GETCHAR_ADDR (PLATFORM_HOST_BASE | 0x0000)
#define PLATFORM_PUTCHAR_ADDR (PLATFORM_HOST_BASE | 0x1000)
#define PLATFORM_FINISH_ADDR  (PLATFORM_HOST_BASE | 0x2000)

#define PLATFORM_ACLINT_MTIMER_FREQ   (50000000)  // 50 MHz on FPGA, more or less
#define PLATFORM_ACLINT_MTIME_ADDR    (PLATFORM_CLINT_BASE | 0xbff8)
#define PLATFORM_ACLINT_MTIME_SIZE    (ACLINT_DEFAULT_MTIME_SIZE)
#define PLATFORM_ACLINT_MTIMECMP_ADDR (PLATFORM_CLINT_BASE | 0x4000)
#define PLATFORM_ACLINT_MTIMECMP_SIZE (ACLINT_DEFAULT_MTIMECMP_SIZE)
#define PLATFORM_ACLINT_MSWI_ADDR     (PLATFORM_CLINT_BASE | 0x0000)
#define PLATFORM_ACLINT_MSWI_SIZE     (ACLINT_MSWI_SIZE)

static void bp_console_putc(char ch)
{
    uintptr_t core_offset = (current_hartid() << 3);
    uintptr_t putchar_ptr = (uintptr_t) PLATFORM_PUTCHAR_ADDR | core_offset;
    char *putchar = (char *) putchar_ptr;
    *putchar = ch;
}

static int bp_console_getc(void)
{
    uintptr_t core_offset = (current_hartid() << 3);
    uintptr_t getchar_ptr = (uintptr_t) PLATFORM_GETCHAR_ADDR | core_offset;
    int *getchar = (int *) getchar_ptr;
    int ch = *getchar;

    return ch;
}

static struct sbi_console_device bp_console = {
    .name = "bp-console",
    .console_putc = bp_console_putc,
    .console_getc = bp_console_getc
};

static void bp_ipi_send(u32 hart_index)
{
    uintptr_t core_offset = (hart_index << 24);
    uintptr_t ipi_ptr = (uintptr_t) PLATFORM_ACLINT_MSWI_ADDR | core_offset;
    int *ipi = (int *) ipi_ptr;
    *ipi = 1;
}

static void bp_ipi_clear(u32 hart_index)
{
    uintptr_t core_offset = (hart_index << 24);
    uintptr_t ipi_ptr = (uintptr_t) PLATFORM_ACLINT_MSWI_ADDR | core_offset;
    int *ipi = (int *) ipi_ptr;
    *ipi = 0;
}

static struct sbi_ipi_device bp_ipi = {
    .name = "bp-ipi",
    .ipi_send = bp_ipi_send,
    .ipi_clear = bp_ipi_clear
};

static u64 bp_timer_value(void)
{
    uintptr_t core_offset = (current_hartid() << 24);
    uintptr_t mtime_ptr = (uintptr_t) PLATFORM_ACLINT_MTIME_ADDR | core_offset;
    int *mtime = (int *) mtime_ptr;
    u64 val = *mtime;

    return val;
}

static void bp_timer_event_start(u64 next_event)
{
    uintptr_t core_offset = (current_hartid() << 24);
    uintptr_t mtimecmp_ptr = (uintptr_t) PLATFORM_ACLINT_MTIMECMP_ADDR | core_offset;
    u64 *mtimecmp = (u64 *) mtimecmp_ptr;
    *mtimecmp = next_event;
}

static void bp_timer_event_stop(void)
{
    uintptr_t core_offset = (current_hartid() << 24);
    uintptr_t mtimecmp_ptr = (uintptr_t) PLATFORM_ACLINT_MTIMECMP_ADDR | core_offset;
    int *mtimecmp = (int *) mtimecmp_ptr;
    *mtimecmp = -1;
}

static struct sbi_timer_device bp_timer = {
    .name = "bp-timer",
    .timer_freq = (unsigned long) PLATFORM_ACLINT_MTIMER_FREQ,
    .timer_value = bp_timer_value,
    .timer_event_start = bp_timer_event_start,
    .timer_event_stop = bp_timer_event_stop
};
static int bp_system_reset_check(u32 type, u32 reason)
{
    switch(type) {
        case SBI_SRST_RESET_TYPE_SHUTDOWN:
            return 1;
    }
    return 0;
}

static void bp_system_reset(u32 type, u32 reason)
{
    switch(type) {
        case SBI_SRST_RESET_TYPE_SHUTDOWN:
            for (int i = 0; i < PLATFORM_HART_COUNT; i++) {
                uintptr_t core_offset = (i << 3);
                uintptr_t poweroff_ptr = (uintptr_t) PLATFORM_FINISH_ADDR | core_offset;
                int *poweroff = (int *) poweroff_ptr;
                *poweroff = reason;
            }
            bp_console_putc('\n');
            bp_console_putc('.');
            bp_console_putc('.');
            bp_console_putc('.');
            bp_console_putc('\n');
            while (1);
    }
}

static struct sbi_system_reset_device bp_reset = {
    .name = "bp-reset",
    .system_reset_check = bp_system_reset_check,
    .system_reset = bp_system_reset
};

/*
 * Platform early initialization.
 */
static int platform_early_init(bool cold_boot)
{
    if (!cold_boot)
        return 0;

    sbi_system_reset_add_device(&bp_reset);

    return 0;
}

/*
 * Platform final initialization.
 */
static int platform_final_init(bool cold_boot)
{
    void *fdt;

    if (!cold_boot)
        return 0;

    fdt = fdt_get_address();
    fdt_fixups(fdt);

    return 0;
}

/*
 * Initialize the platform console.
 */
static int platform_console_init(void)
{
    sbi_console_set_device(&bp_console);

    return 0;
}

/*
 * Initialize IPI for current HART.
 */
static int platform_ipi_init(bool cold_boot)
{
    if (!cold_boot)
        return 0;

    sbi_ipi_set_device(&bp_ipi);

    return 0;
}

/*
 * Initialize platform timer for current HART.
 */
static int platform_timer_init(bool cold_boot)
{
    if (!cold_boot)
        return 0;

    sbi_timer_set_device(&bp_timer);

    return 0;
}

/*
 * Platform descriptor.
 */
const struct sbi_platform_operations platform_ops = {
    .early_init   = platform_early_init,
    .final_init   = platform_final_init,
    .console_init = platform_console_init,
    .ipi_init     = platform_ipi_init,
    .timer_init   = platform_timer_init
};

const struct sbi_platform platform = {
    .opensbi_version   = OPENSBI_VERSION,
    .platform_version  = SBI_PLATFORM_VERSION(0x0, 0x00),
    .name              = "blackparrot",
    .features          = SBI_PLATFORM_DEFAULT_FEATURES,
    .hart_count        = PLATFORM_HART_COUNT,
    .hart_stack_size   = SBI_PLATFORM_DEFAULT_HART_STACK_SIZE,
    .heap_size         = SBI_PLATFORM_DEFAULT_HEAP_SIZE(1),
    .platform_ops_addr = (unsigned long)&platform_ops
};
