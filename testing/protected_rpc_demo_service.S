/*
 * Tiny protected-library service used by mt_protected_rpc_library_test.
 * The whole service occupies one page that is mapped only by the server's
 * page table.  Its private and shared virtual addresses are part of this
 * deliberately small test ABI.
 */

  .section .text.bp_rpc_demo_service, "ax", @progbits
  .option push
  .option norvc
  .balign 4096

  .globl bp_rpc_demo_server_bootstrap
  .type bp_rpc_demo_server_bootstrap, @function
bp_rpc_demo_server_bootstrap:
  /* Establish server-private state and tell the monitor that context 1 ran. */
  li t0, 0x40000
  li t1, 0x1000
  sd t1, 0(t0)
  li t0, 0x70000
  li t1, 1
  sd t1, 64(t0)

  /* This setup-time raw return is disabled after M mode installs the
   * protected descriptor. */
  csrwi 0x800, 0
1:
  j 1b
  .size bp_rpc_demo_server_bootstrap, .-bp_rpc_demo_server_bootstrap

  .balign 64
  .globl bp_rpc_demo_service_entry
  .type bp_rpc_demo_service_entry, @function
bp_rpc_demo_service_entry:
  /* Reject an invalid caller-provided range before touching private state. */
  li t2, 8
  bne a1, t2, 3f
  li t2, 4088
  bgtu a0, t2, 3f
  li t2, 0x70000
  add t2, t2, a0

  /* Counter state is private to the server even though the caller uses the
   * same virtual address for a different physical page. */
  li t0, 0x40000
  ld t1, 0(t0)
  addi t1, t1, 1
  sd t1, 0(t0)

  /* a0 is an offset, not a caller virtual address.  Validate the entire
   * eight-byte range, translate it with the server's distinct shared base,
   * then update the shared word by a2 + private_counter. */
  ld a0, 0(t2)
  add a0, a0, a2
  add a0, a0, t1
  sd a0, 0(t2)

  li t0, 0x70000
  sd t1, 16(t0)
  csrw 0x809, a0
3:
  li a0, -1
  csrw 0x809, a0
2:
  j 2b
  .size bp_rpc_demo_service_entry, .-bp_rpc_demo_service_entry

  .option pop
