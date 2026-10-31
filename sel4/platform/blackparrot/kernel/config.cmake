# SPDX-License-Identifier: GPL-2.0-only

declare_platform(blackparrot KernelPlatformBlackParrot PLAT_BLACKPARROT KernelArchRiscV)

if(KernelPlatformBlackParrot)
    declare_seL4_arch(riscv64)
    config_set(KernelRiscVPlatform RISCV_PLAT "blackparrot")
    config_set(KernelPlatformFirstHartID FIRST_HART_ID 0)
    config_set(KernelOpenSBIPlatform OPENSBI_PLATFORM "generic")
    list(APPEND KernelDTSList "tools/dts/blackparrot.dts")
    list(APPEND KernelDTSList "src/plat/blackparrot/overlay-blackparrot.dts")
    declare_default_headers(
        TIMER_FREQUENCY 8000000
        MAX_IRQ 0
        INTERRUPT_CONTROLLER drivers/irq/riscv_plic_dummy.h
    )
else()
    unset(KernelPlatformFirstHartID CACHE)
endif()

add_sources(
    DEP "KernelPlatformBlackParrot"
    CFILES src/plat/blackparrot/machine/rpc.c
)
