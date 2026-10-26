#define _GNU_SOURCE

/* Exercise pinned physical hints across a real process address-space switch.
 * Each process registers its own page, alternates on pipes, and checks its
 * data. Mode 2 leaves the child's pins to the task-exit drain hook.
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>

#define PR_BP_PREVIEW_GET_COUNT 0x42505057
#define PR_BP_PREVIEW_PIN_SET 0x42505059

enum { lines = 4, rounds = 32, line_bytes = 64, page_bytes = 4096 };

static void fail(const char *what)
{
	perror(what);
	exit(1);
}

static void transfer(int fd, void *data, size_t count, int send)
{
	ssize_t got = send ? write(fd, data, count) : read(fd, data, count);

	if (got != (ssize_t)count)
		fail(send ? "write pipe" : "read pipe");
}

static void participant(int recv_fd, int send_fd, int child, int mode)
{
	volatile uint64_t *page;
	unsigned long addr[lines] = {};
	unsigned long before = 0, after = 0;
	unsigned int round, lane;
	int enabled = mode != 0;
	char token = 'x';

	page = mmap(NULL, page_bytes, PROT_READ | PROT_WRITE,
		    MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (page == MAP_FAILED)
		fail("mmap target");
	for (lane = 0; lane < lines; lane++) {
		addr[lane] = (unsigned long)&page[lane * line_bytes / sizeof(*page)];
		*(volatile uint64_t *)addr[lane] = 0x12340000UL + child * 256 + lane;
	}
	if (enabled && prctl(PR_BP_PREVIEW_PIN_SET, addr[0], addr[1],
			     addr[2], addr[3]))
		fail("pin preview page");
	if (enabled) {
		before = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (before == (unsigned long)-1)
			fail("read preview count");
	}

	if (child)
		transfer(send_fd, &token, 1, 1);
	else
		transfer(recv_fd, &token, 1, 0);
	for (round = 0; round < rounds; round++) {
		if (!child)
			transfer(send_fd, &token, 1, 1);
		transfer(recv_fd, &token, 1, 0);
		for (lane = 0; lane < lines; lane++) {
			uint64_t value = *(volatile uint64_t *)addr[lane];

			if (value != 0x12340000UL + child * 256 + lane) {
				fprintf(stderr, "wrong target data: child=%d round=%u lane=%u value=%llu\n",
					child, round, lane, (unsigned long long)value);
				exit(1);
			}
		}
		if (child)
			transfer(send_fd, &token, 1, 1);
	}
	if (enabled) {
		after = prctl(PR_BP_PREVIEW_GET_COUNT, 0UL, 0UL, 0UL, 0UL);
		if (after == (unsigned long)-1)
			fail("read final preview count");
	}
	if (enabled && after <= before) {
		fprintf(stderr, "no cross-mm preview hooks: child=%d before=%lu after=%lu\n",
			child, before, after);
		exit(1);
	}
	/* Mode 2 leaves the child's pins for the task-exit drain path. */
	if (enabled && !(mode == 2 && child)
	    && prctl(PR_BP_PREVIEW_PIN_SET, 0UL, 0UL, 0UL, 0UL))
		fail("release preview page");
	printf("PHYSICAL_PREVIEW child=%d mode=%d hooks=%lu rounds=%d PASS\n",
	       child, mode, after - before, rounds);
	if (munmap((void *)page, page_bytes))
		fail("munmap target");
}

int main(int argc, char **argv)
{
	int to_child[2], to_parent[2], status;
	int mode = argc == 2 && argv[1][0] && !argv[1][1]
		? argv[1][0] - '0' : -1;
	pid_t child;

	if (mode < 0 || mode > 2) {
		fprintf(stderr, "usage: %s 0|1|2\n", argv[0]);
		return 2;
	}
	if (pipe(to_child) || pipe(to_parent))
		fail("pipe");
	child = fork();
	if (child < 0)
		fail("fork");
	if (!child) {
		close(to_child[1]);
		close(to_parent[0]);
		participant(to_child[0], to_parent[1], 1, mode);
		return 0;
	}
	close(to_child[0]);
	close(to_parent[1]);
	participant(to_parent[0], to_child[1], 0, mode);
	if (waitpid(child, &status, 0) != child)
		fail("waitpid");
	if (!WIFEXITED(status) || WEXITSTATUS(status)) {
		fprintf(stderr, "child failed: status=%d\n", status);
		return 1;
	}
	puts("PHYSICAL_PREVIEW_SMOKE PASS");
	return 0;
}
