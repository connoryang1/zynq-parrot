TOP ?= $(shell git rev-parse --show-toplevel)

SDK_LINUX_DIR ?= $(TOP)/import/black-parrot-sdk/linux
SDK_OPENSBI_DIR ?= $(SDK_LINUX_DIR)/opensbi
LINUX_RISCV ?= $(SDK_LINUX_DIR)/linux.riscv
BP_LINUX_CC ?= riscv64-unknown-linux-gnu-gcc
BP_LINUX_CC_PATH := $(shell command -v $(BP_LINUX_CC) 2>/dev/null)
BP_LINUX_PREFIX ?= $(patsubst %gcc,%,$(BP_LINUX_CC_PATH))
BP_LINUX_TOOLCHAIN_BIN ?= $(dir $(BP_LINUX_CC_PATH))
BP_LINUX_TARGET ?= $(patsubst %-gcc,%,$(notdir $(BP_LINUX_CC_PATH)))
BP_OBJCOPY ?= $(TOP)/install/bin/riscv64-unknown-elf-objcopy
BP_DTS_PYTHON ?= python3
BP_CPIO ?= cpio
NBF_TOOL ?= $(TOP)/import/black-parrot/bp_common/software/py/nbf.py
NBF_CSR_CHECK ?= $(TOP)/codex-skills/bp-fpga-synthesis/scripts/check_nbf_csr_collisions.sh
BASELINE_LINUX_NBF ?= $(TOP)/riscv/linux/linux-6.6-jhumphri-20250125.nbf

OUT ?= $(CURDIR)/out
APP := $(OUT)/ctxtsw_user_smoke
TINY_APP := $(OUT)/ctxtsw_user_tiny
APP_NBF := $(OUT)/linux-ctxtsw-user-smoke.nbf
TINY_INIT_NBF := $(OUT)/linux-ctxtsw-tiny-init.nbf
DEMO_GENDTS := $(CURDIR)/gendts_ctxtsw.py
INIT_SCRIPT := $(CURDIR)/rootfs-overlay/etc/init.d/S200ctxtsw_user_smoke.sh
OPENSBI_PLATFORM_OVERLAY := $(CURDIR)/opensbi-platform/blackparrot
GENERATED_DTS := $(SDK_LINUX_DIR)/work/opensbi/platform/generic/blackparrot/blackparrot.dts
GENERATED_DTB := $(SDK_LINUX_DIR)/work/opensbi/platform/generic/blackparrot/blackparrot.dtb
ROOTFS_CPIO := $(SDK_LINUX_DIR)/work/buildroot/images/rootfs.cpio
KERNEL_INITRAMFS := $(SDK_LINUX_DIR)/work/buildroot/build/linux-6.6/usr/initramfs_inc_data
VMLINUX_BIN := $(SDK_LINUX_DIR)/work/buildroot/images/vmlinux.bin
OPENSBI_PAYLOAD := $(SDK_LINUX_DIR)/work/opensbi/platform/generic/blackparrot/firmware/fw_payload.elf
TINY_BOOTARGS := console=hvc0 loglevel=8 rdinit=/ctxtsw_user_tiny
TINY_TARGET_SYSCALL ?= 1

CFLAGS := -O2 -static -Wall -Wextra -Werror \
  -march=rv64imafdc_zicsr -mabi=lp64d -mcmodel=medany

.PHONY: app tiny check-linux-cc check-image-toolchain stage-opensbi-platform stage-rootfs linux-image tiny-init-linux-image tiny-init-linux-image-resume validate-tiny-init-image package-tiny-init-nbf emit-tiny-transfer clean

app: $(APP)

$(APP): ctxtsw_user_smoke.c
	@mkdir -p $(OUT)
	$(BP_LINUX_CC) $(CFLAGS) -o $@ $<

# No-libc version for the first interactive-shell demonstration.  Its small
# static ELF can be transferred through the BlackParrot console without
# rebuilding Buildroot or the kernel.
tiny: $(TINY_APP)

$(TINY_APP): ctxtsw_user_tiny.c
	@mkdir -p $(OUT)
	$(BP_LINUX_CC) -Os -static -nostdlib -nostartfiles -ffreestanding \
	  -fno-stack-protector -ffixed-s11 -Wl,-e,_start -Wl,--build-id=none \
	  -DBP_TARGET_SYSCALL=$(TINY_TARGET_SYSCALL) \
	  -march=rv64imafdc_zicsr -mabi=lp64d -mcmodel=medany -o $@ $<

# Print a self-contained command suitable for an interactive BusyBox shell.
# The shell needs only its standard base64 applet and a writable /tmp.
emit-tiny-transfer: check-linux-cc tiny
	@printf "base64 -d > /tmp/ctxtsw_user_tiny <<'BP_EOF'\\n"
	@base64 -w 76 $(TINY_APP)
	@printf '%s\n' 'BP_EOF' 'chmod +x /tmp/ctxtsw_user_tiny' '/tmp/ctxtsw_user_tiny' 'echo CONTEXT_SWITCH_EXIT=$$?'

check-linux-cc:
	@command -v $(BP_LINUX_CC) >/dev/null || { \
	  echo "missing BP_LINUX_CC=$(BP_LINUX_CC); point it at the matching Linux SDK compiler" >&2; exit 2; \
	}
	@command -v $(BP_LINUX_PREFIX)strip >/dev/null || { \
	  echo "missing matching Linux strip tool $(BP_LINUX_PREFIX)strip" >&2; exit 2; \
	}
	@command -v $(BP_LINUX_PREFIX)objcopy >/dev/null || { \
	  echo "missing matching Linux objcopy tool $(BP_LINUX_PREFIX)objcopy" >&2; exit 2; \
	}

# Building an image additionally needs the bare-metal objcopy and the NBF
# collision guard.  Keep those separate from the tiny shell-transfer path,
# which only builds a Linux ELF and should have no unnecessary dependency.
check-image-toolchain: check-linux-cc
	@command -v $(BP_OBJCOPY) >/dev/null || { \
	  echo "missing BP_OBJCOPY=$(BP_OBJCOPY)" >&2; exit 2; \
	}
	@command -v $(BP_DTS_PYTHON) >/dev/null || { \
	  echo "missing BP_DTS_PYTHON=$(BP_DTS_PYTHON)" >&2; exit 2; \
	}
	@command -v $(BP_CPIO) >/dev/null || { \
	  echo "missing BP_CPIO=$(BP_CPIO)" >&2; exit 2; \
	}
	@command -v dtc >/dev/null || { echo "missing dtc" >&2; exit 2; }
	@command -v gzip >/dev/null || { echo "missing gzip" >&2; exit 2; }
	@test -x $(NBF_CSR_CHECK)
	@test -f $(BASELINE_LINUX_NBF) || { \
	  echo "missing BASELINE_LINUX_NBF=$(BASELINE_LINUX_NBF)" >&2; exit 2; \
	}
	$(NBF_CSR_CHECK) $(BASELINE_LINUX_NBF) 800 801 802 803 804

# The pinned OpenSBI revision does not track BlackParrot's board platform even
# though the SDK Makefile selects it.  Materialize the known-working platform
# overlay explicitly so a clean checkout does not depend on Jack's old home
# directory or an untracked nested-submodule file.
stage-opensbi-platform:
	@test -f $(OPENSBI_PLATFORM_OVERLAY)/platform.c
	install -D -m 0644 $(OPENSBI_PLATFORM_OVERLAY)/Kconfig $(SDK_OPENSBI_DIR)/platform/generic/blackparrot/Kconfig
	install -D -m 0644 $(OPENSBI_PLATFORM_OVERLAY)/objects.mk $(SDK_OPENSBI_DIR)/platform/generic/blackparrot/objects.mk
	install -D -m 0644 $(OPENSBI_PLATFORM_OVERLAY)/platform.c $(SDK_OPENSBI_DIR)/platform/generic/blackparrot/platform.c
	install -D -m 0644 $(OPENSBI_PLATFORM_OVERLAY)/configs/defconfig $(SDK_OPENSBI_DIR)/platform/generic/blackparrot/configs/defconfig

# Build only the application and install it into an already-created SDK
# sysroot.  This makes application-only edits cheap once a Linux work tree is
# prepared, and keeps all generated rootfs state outside the source overlay.
stage-rootfs: check-image-toolchain app
	@test -d $(SDK_LINUX_DIR)/work/sysroot || { \
	  echo "missing SDK sysroot; run make -C $(SDK_LINUX_DIR) sysroot first" >&2; exit 2; \
	}
	install -D -m 0755 $(APP) $(SDK_LINUX_DIR)/work/sysroot/usr/bin/ctxtsw_user_smoke
	install -D -m 0755 $(INIT_SCRIPT) $(SDK_LINUX_DIR)/work/sysroot/etc/init.d/S200ctxtsw_user_smoke.sh

# Rebuild a boot image with the smoke executable in its initramfs.  The SDK
# Makefile does not track overlay-file changes, so clean_sysroot is deliberate:
# it prevents a stale rootfs from being packaged as a purported demo image.
linux-image: check-image-toolchain stage-opensbi-platform
	$(MAKE) -C $(SDK_LINUX_DIR) clean_sysroot
	$(MAKE) -C $(SDK_LINUX_DIR) sysroot WITH_SHELL=$(INIT_SCRIPT)
	$(MAKE) stage-rootfs
	$(MAKE) -C $(SDK_LINUX_DIR) linux.riscv WITH_SHELL=$(INIT_SCRIPT) \
	  LINUX_TARGET=$(BP_LINUX_TARGET)
	@mkdir -p $(OUT)
	$(BP_OBJCOPY) -O verilog $(LINUX_RISCV) $(OUT)/linux-ctxtsw-user-smoke.mem
	sed -i 's/@8/@0/g' $(OUT)/linux-ctxtsw-user-smoke.mem
	python3 $(NBF_TOOL) --skip_zeros --config --debug \
	  --mem $(OUT)/linux-ctxtsw-user-smoke.mem --ncpus 1 > $(APP_NBF)
	@echo "NBF=$(APP_NBF)"
	@sha256sum $(APP_NBF)

# Produce the acceptance image used for the FPGA/Linux proof.  A clean SDK
# work directory is intentional: the SDK's fine-grained clean targets do not
# reliably invalidate its embedded initramfs, so reusing them could package a
# stale root filesystem.  Linux runs the tiny static ELF directly as PID 1,
# before BusyBox rcS/sysctl, and the program powers off only after a proven
# nonresident 0 -> 2 -> 0 handoff.
tiny-init-linux-image: check-image-toolchain tiny stage-opensbi-platform
	$(MAKE) -C $(SDK_LINUX_DIR) clean_buildroot
	$(MAKE) -C $(SDK_LINUX_DIR) sysroot WITH_SHELL=
	install -D -m 0755 $(TINY_APP) $(SDK_LINUX_DIR)/work/sysroot/ctxtsw_user_tiny
	PATH=$(BP_LINUX_TOOLCHAIN_BIN):$$PATH \
	BP_BASE_GENDTS=$(SDK_LINUX_DIR)/gendts.py \
	BP_DEMO_BOOTARGS='$(TINY_BOOTARGS)' \
	$(MAKE) -C $(SDK_LINUX_DIR) linux.riscv WITH_SHELL= \
	  LINUX_TARGET=$(BP_LINUX_TARGET) \
	  PYTHON=$(BP_DTS_PYTHON) GENDTS_PY=$(DEMO_GENDTS)
	$(MAKE) package-tiny-init-nbf

# Resume only after a full tiny-init build reached a later packaging/toolchain
# failure.  This preserves the compiled Buildroot/kernel checkpoint while
# retaining the same explicit DTS generator and toolchain selection.
tiny-init-linux-image-resume: check-image-toolchain tiny stage-opensbi-platform
	@test -d $(SDK_LINUX_DIR)/work/buildroot || { \
	  echo "missing prepared Buildroot work tree; run tiny-init-linux-image" >&2; exit 2; \
	}
	install -D -m 0755 $(TINY_APP) $(SDK_LINUX_DIR)/work/sysroot/ctxtsw_user_tiny
	PATH=$(BP_LINUX_TOOLCHAIN_BIN):$$PATH \
	BP_BASE_GENDTS=$(SDK_LINUX_DIR)/gendts.py \
	BP_DEMO_BOOTARGS='$(TINY_BOOTARGS)' \
	$(MAKE) -C $(SDK_LINUX_DIR) linux.riscv WITH_SHELL= \
	  LINUX_TARGET=$(BP_LINUX_TARGET) \
	  PYTHON=$(BP_DTS_PYTHON) GENDTS_PY=$(DEMO_GENDTS)
	$(MAKE) package-tiny-init-nbf

# Fail closed if either the DTS or initramfs is stale.  An NBF built from a
# mismatched Linux image is not useful evidence even when its packaging works.
validate-tiny-init-image: check-image-toolchain tiny
	@test -f $(GENERATED_DTS) || { echo "missing generated DTS $(GENERATED_DTS)" >&2; exit 2; }
	@grep -Fqx '        bootargs = "$(TINY_BOOTARGS)";' $(GENERATED_DTS) || { \
	  echo "generated DTS does not contain the exact tiny-init bootargs" >&2; exit 2; \
	}
	@test -f $(ROOTFS_CPIO) || { echo "missing initramfs $(ROOTFS_CPIO)" >&2; exit 2; }
	@tmpdir=$$(mktemp -d); trap 'rm -rf "$$tmpdir"' EXIT HUP INT TERM; \
	  cd "$$tmpdir"; \
	  $(BP_CPIO) --quiet -id 'ctxtsw_user_tiny' < $(ROOTFS_CPIO); \
	  test -x ctxtsw_user_tiny || { echo "initramfs PID 1 is missing or not executable" >&2; exit 2; }; \
	  cmp -s ctxtsw_user_tiny $(TINY_APP) || { \
	    echo "embedded ctxtsw_user_tiny differs from the current ELF" >&2; exit 2; \
	  }
	@test -f $(GENERATED_DTB) || { echo "missing generated DTB $(GENERATED_DTB)" >&2; exit 2; }
	@bootargs=$$(dtc -I dtb -O dts $(GENERATED_DTB) 2>/dev/null \
	  | sed -n 's/^[[:space:]]*bootargs = "\(.*\)";[[:space:]]*$$/\1/p'); \
	  test "$$bootargs" = '$(TINY_BOOTARGS)' || { \
	    echo "generated DTB does not contain the exact tiny-init bootargs" >&2; exit 2; \
	  }
	@test -f $(KERNEL_INITRAMFS) || { echo "missing kernel initramfs input $(KERNEL_INITRAMFS)" >&2; exit 2; }
	@tmpdir=$$(mktemp -d); trap 'rm -rf "$$tmpdir"' EXIT HUP INT TERM; \
	  gzip -cd $(KERNEL_INITRAMFS) > "$$tmpdir/initramfs.cpio"; \
	  cmp -s "$$tmpdir/initramfs.cpio" $(ROOTFS_CPIO) || { \
	    echo "kernel embedded initramfs input differs from rootfs.cpio" >&2; exit 2; \
	  }
	@test -f $(VMLINUX_BIN) && test $(VMLINUX_BIN) -nt $(KERNEL_INITRAMFS) || { \
	  echo "vmlinux payload is missing or older than its initramfs" >&2; exit 2; \
	}
	@test -f $(OPENSBI_PAYLOAD) \
	  && test $(OPENSBI_PAYLOAD) -nt $(VMLINUX_BIN) \
	  && test $(OPENSBI_PAYLOAD) -nt $(GENERATED_DTB) || { \
	  echo "OpenSBI payload is missing or older than its kernel/DTB inputs" >&2; exit 2; \
	}
	@cmp -s $(OPENSBI_PAYLOAD) $(LINUX_RISCV) || { \
	  echo "linux.riscv differs from the validated OpenSBI payload" >&2; exit 2; \
	}
	@echo "TINY_INIT_IMAGE_VALIDATED dts=$(GENERATED_DTS) dtb=$(GENERATED_DTB) rootfs=$(ROOTFS_CPIO) payload=$(LINUX_RISCV)"
	@sha256sum $(TINY_APP) $(ROOTFS_CPIO) $(KERNEL_INITRAMFS) $(GENERATED_DTB) $(VMLINUX_BIN) $(OPENSBI_PAYLOAD) $(LINUX_RISCV)

package-tiny-init-nbf: validate-tiny-init-image
	@mkdir -p $(OUT)
	$(BP_OBJCOPY) -O verilog $(LINUX_RISCV) $(OUT)/linux-ctxtsw-tiny-init.mem
	sed -i 's/@8/@0/g' $(OUT)/linux-ctxtsw-tiny-init.mem
	python3 $(NBF_TOOL) --skip_zeros --config --debug \
	  --mem $(OUT)/linux-ctxtsw-tiny-init.mem --ncpus 1 > $(TINY_INIT_NBF)
	@echo "NBF=$(TINY_INIT_NBF)"
	@sha256sum $(TINY_APP) $(TINY_INIT_NBF)

clean:
	rm -rf $(OUT)
