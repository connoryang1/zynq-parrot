#define GP0_ADDR_BASE 0x40000000U
#include "ps.hpp"
static_assert(GP0_RD_CSR_SYS_RESETN==0x40000000U,"old reset");
static_assert(GP0_RD_PL2PS_FIFO_DATA==0x40000014U,"old fifo data");
static_assert(GP0_RD_PL2PS_FIFO_CTRS==0x40000018U,"old fifo count");
static_assert(GP0_RD_PS2PL_FIFO_CTRS==0x4000001cU,"old fifo count");
static_assert(GP0_RD_MINSTRET_0==0x40000020U&&GP0_RD_MINSTRET_1==0x40000024U,"old instret");
static_assert(GP0_RD_MEM_PROF_0==0x40000028U&&GP0_RD_MEM_PROF_3==0x40000034U,"old profiler");
static_assert(GP0_RD_BOOTROM_DATA==0x40000038U,"old bootrom");
static_assert(GP0_RD_RETAINED_HITS==0x4000003cU,"new user reg7");
static_assert(GP0_RD_RETAINED_PUBLISHED==0x40000040U,"new user reg8");
static_assert(GP0_RD_RETAINED_WRITES==0x40000044U,"new user reg9");
static_assert(GP0_WR_CSR_SYS_RESETN==0x40000000U&&GP0_WR_PS2PL_FIFO_DATA==0x40000014U,"old writes");
