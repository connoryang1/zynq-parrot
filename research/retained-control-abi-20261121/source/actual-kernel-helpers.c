#define CONFIG_MMU 1
#define __LINUX_BITS_H
#include <asm/asm-extable.h>
typedef unsigned long u64;
#define ENODEV 19
extern void preempt_disable(void);
extern void preempt_enable(void);
static int bp_retained_probe(u64 *status)
{
	unsigned long err = 0, value = 0;

	asm volatile("1: csrr %[value], 0x5c2\n"
		     "2:\n"
		     _ASM_EXTABLE_UACCESS_ERR_ZERO(1b, 2b, %[err], %[value])
		     : [err] "+&r" (err), [value] "+&r" (value)
		     : : "memory");
	if (err || !(value & (1UL << 63)))
		return -ENODEV;
	*status = value;
	return 0;
}

static int bp_retained_control(unsigned long mask)
{
	u64 status;
	int error;

	preempt_disable();
	error = bp_retained_probe(&status);
	if (!error)
		/* Submission only: clears stores, without invalidating normal L1I. */
		asm volatile("csrw 0x5c2, %0\n" : : "r" (mask) : "memory");
	preempt_enable();
	return error;
}

static int bp_retained_status(u64 *status)
{
	int error;

	preempt_disable();
	error = bp_retained_probe(status);
	preempt_enable();
	return error;
}

int check_control(unsigned long mask) { return bp_retained_control(mask); }
int check_status(u64 *status) { return bp_retained_status(status); }
