# Verilated -*- Makefile -*-
# DESCRIPTION: Verilator output: Makefile for building Verilated archive or executable
#
# Execute this makefile from the object directory:
#    make -f Vbsg_nonsynth_zynq_testbench.mk

default: Vbsg_nonsynth_zynq_testbench

### Constants...
# Perl executable (from $PERL, defaults to 'perl' if not set)
PERL = perl
# Python3 executable (from $PYTHON3, defaults to 'python3' if not set)
PYTHON3 = python3
# Path to Verilator kit (from $VERILATOR_ROOT)
VERILATOR_ROOT = /home/coyang/zynq-parrot/install/share/verilator
# SystemC include directory with systemc.h (from $SYSTEMC_INCLUDE)
SYSTEMC_INCLUDE ?= 
# SystemC library directory with libsystemc.a (from $SYSTEMC_LIBDIR)
SYSTEMC_LIBDIR ?= 

### Switches...
# C++ code coverage  0/1 (from --prof-c)
VM_PROFC = 0
# SystemC output mode?  0/1 (from --sc)
VM_SC = 0
# Legacy or SystemC output mode?  0/1 (from --sc)
VM_SP_OR_SC = $(VM_SC)
# Deprecated
VM_PCLI = 1
# Deprecated: SystemC architecture to find link library path (from $SYSTEMC_ARCH)
VM_SC_TARGET_ARCH = linux

### Vars...
# Design prefix (from --prefix)
VM_PREFIX = Vbsg_nonsynth_zynq_testbench
# Module prefix (from --prefix)
VM_MODPREFIX = Vbsg_nonsynth_zynq_testbench
# User CFLAGS (from -CFLAGS on Verilator command line)
VM_USER_CFLAGS = \
	-DZYNQ_AXI_TIMEOUT=100000 -D_DEFAULT_SOURCE -D_BSD_SOURCE -DGP0_ADDR_BASE=0x40000000U -DGP0_HIER_BASE=TOP.bsg_nonsynth_zynq_testbench.axil0 -DGP1_ADDR_BASE=0x80000000U -DGP1_HIER_BASE=TOP.bsg_nonsynth_zynq_testbench.axil1 -DGP2_ADDR_BASE=0x80000000U -DGP2_HIER_BASE=TOP.bsg_nonsynth_zynq_testbench.axil2 -DWATCHDOG_ENABLE -DHP0_ADDR_BASE=0x0000000U -DAXI_MEM_ENABLE -DHP1_ADDR_BASE=0x1000000U -DHP1_HIER_BASE=TOP.bsg_nonsynth_zynq_testbench.axil4 -DSCRATCHPAD_ENABLE -DGP0_ENABLE=1 -DGP0_ADDR_WIDTH=10 -DGP0_DATA_WIDTH=32 -DGP1_ENABLE=1 -DGP1_ADDR_WIDTH=30 -DGP1_DATA_WIDTH=32 -DGP2_ENABLE=1 -DGP2_ADDR_WIDTH=30 -DGP2_DATA_WIDTH=32 -DHP0_ENABLE=1 -DHP0_ADDR_WIDTH=32 -DHP0_DATA_WIDTH=64 -DHP1_ENABLE=1 -DHP1_ADDR_WIDTH=32 -DHP1_DATA_WIDTH=32 -DACLK_MHZ=20 -DRTCLK_MHZ=8 -DRT_CLK_ENABLE=1 -DTAG_ENABLE=1 -DBP_NCPUS=1 -DBP_CUSTOM_BASE_CFG=bp_unicore_zynqparrot_cfg_p -DBP_NUM_THREADS=2 -DBP_NUM_CONTEXTS=4 -DBRANCH_METADATA_FWD_WIDTH=50 -DHOST_ZYNQ -DBSG_NO_TIMESCALE -DSIMULATION -DBP_AXI_MEM_PIPELINED -DBP_AXI_MEM_READ_LATENCY=40 -DBP_AXI_MEM_READ_QUEUE_DEPTH=4 -I/home/coyang/zynq-parrot-linux-research/cosim/black-parrot-example/verilator -I/home/coyang/zynq-parrot-linux-research/cosim/include/common -I/home/coyang/zynq-parrot-linux-research/cosim/include/verilator -I/home/coyang/zynq-parrot-linux-research/install/include -I/home/coyang/zynq-parrot-linux-research/import/basejump_stl/bsg_mem -I/home/coyang/zynq-parrot-linux-research/import/black-parrot-subsystems/blackparrot/src -I/home/coyang/zynq-parrot-linux-research/import/bsg_replicant/libraries -I/home/coyang/zynq-parrot-linux-research/import/basejump_stl/bsg_test -L/home/coyang/zynq-parrot-linux-research/install/lib \

# User LDLIBS (from -LDFLAGS on Verilator command line)
VM_USER_LDLIBS = \
	 -L/home/coyang/zynq-parrot-linux-research/install/lib -lboost_coroutine -lboost_context -lboost_system \
	-lz \

# User .cpp files (from .cpp's on Verilator command line)
VM_USER_CLASSES = \
	ps \
	main \
	bsg_nonsynth_dpi_clock_gen \

# User .cpp directories (from .cpp's on Verilator command line)
VM_USER_DIR = \
	../../../../home/coyang/zynq-parrot-linux-research/cosim/black-parrot-example \
	../../../../home/coyang/zynq-parrot-linux-research/cosim/black-parrot-example/verilator \
	../../../../home/coyang/zynq-parrot-linux-research/cosim/src \
	../../../../home/coyang/zynq-parrot-linux-research/import/basejump_stl/bsg_test \


### Default rules...
# Include list of all generated classes
include Vbsg_nonsynth_zynq_testbench_classes.mk
# Include global rules
include $(VERILATOR_ROOT)/include/verilated.mk

### Executable rules... (from --exe)
VPATH += $(VM_USER_DIR)

ps.o: /home/coyang/zynq-parrot-linux-research/cosim/black-parrot-example/ps.cpp 
	$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST)  -c -o $@ $<
main.o: /home/coyang/zynq-parrot-linux-research/cosim/src/main.cpp 
	$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST)  -c -o $@ $<
bsg_nonsynth_dpi_clock_gen.o: /home/coyang/zynq-parrot-linux-research/import/basejump_stl/bsg_test/bsg_nonsynth_dpi_clock_gen.cpp 
	$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST)  -c -o $@ $<

### Link rules... (from --exe)
Vbsg_nonsynth_zynq_testbench: $(VK_USER_OBJS) $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a $(VM_HIER_LIBS)
	$(LINK) $(LDFLAGS) $^ $(LOADLIBES) $(LDLIBS) $(LIBS) $(SC_LIBS) -o $@


# Verilated -*- Makefile -*-
