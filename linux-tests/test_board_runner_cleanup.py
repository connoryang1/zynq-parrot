"""Execute only the real board helper's exit cleanup in an isolated host shell.

Lock and status paths are fixture variables; HOME is never reassigned. No
board runner, SSH, sync executable or control program is launched.
"""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'codex-skills/bp-fpga-synthesis/scripts/board_run_pynq_interactive.sh'


class BoardCleanupTests(unittest.TestCase):
    def run_cleanup(self, program_rc, sync_rc=0):
        source = SOURCE.read_text()
        cleanup = source[source.index('cleanup() {\n'):source.index('\ntrap cleanup EXIT')]
        with tempfile.TemporaryDirectory(prefix='runner-cleanup-host-') as directory:
            root = Path(directory)
            lock, status, events = root / 'lock', root / 'status', root / 'events'
            lock.mkdir()
            (lock / 'owner').write_text('fixture-owned lock\n')
            shell = r'''
set -euo pipefail
lock=$1
status=$2
events=$3
sync_rc=$4
program_rc=$5
printf() {
  case "$1" in BOARD_RUNNER_SOURCE_SHA256=*)
    [[ "$(cat "$events")" == *sync ]] || exit 97
    builtin printf 'marker\n' >> "$events"
  esac
  builtin printf "$@"
}
rm() {
  [[ "$(cat "$status")" == "RUNNER_EXIT=$program_rc" ]] || exit 94
  printf 'rm\n' >> "$events"; command rm "$@"
}
rmdir() {
  [[ ! -e "$lock/owner" ]] || exit 94
  printf 'rmdir\n' >> "$events"; command rmdir "$@"
}
sync() {
  [[ ! -e "$lock" && -f "$status" ]] || exit 95
  [[ "$(cat "$status")" == "RUNNER_EXIT=$program_rc" ]] || exit 96
  printf 'sync\n' >> "$events"
  return "$sync_rc"
}
'''
            shell += cleanup + '\ntrap cleanup EXIT\nprintf "program-complete\\n" >> "$events"\nexit "$program_rc"\n'
            run = subprocess.run(['bash', '-c', shell, str(SOURCE), str(lock), str(status),
                                  str(events), str(sync_rc), str(program_rc)],
                                 capture_output=True, text=True, timeout=10)
            return run, events.read_text().splitlines(), status.read_text(), lock.exists()

    def test_success_persists_status_and_lock_removal_before_sync(self):
        run, events, status, lock_exists = self.run_cleanup(0)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(events, ['program-complete', 'rm', 'rmdir', 'sync', 'marker'])
        self.assertEqual(status, 'RUNNER_EXIT=0\n')
        self.assertFalse(lock_exists)
        self.assertEqual(run.stdout, 'BOARD_RUNNER_SOURCE_SHA256=' + hashlib.sha256(SOURCE.read_bytes()).hexdigest() + '\n')

    def test_program_failure_code_is_preserved_after_successful_sync(self):
        for program_rc in (1, 37, 75, 124):
            with self.subTest(program_rc=program_rc):
                run, events, status, lock_exists = self.run_cleanup(program_rc)
                self.assertEqual(run.returncode, program_rc, run.stderr)
                self.assertEqual(status, f'RUNNER_EXIT={program_rc}\n')
                self.assertEqual(events[-1], 'marker')
                self.assertEqual(events.count('sync'), 1)
                self.assertFalse(lock_exists)
                self.assertIn('BOARD_RUNNER_SOURCE_SHA256=', run.stdout)

    def test_sync_failure_fails_closed_without_replacing_program_failure(self):
        for program_rc, expected_rc in ((0, 74), (37, 37), (75, 75)):
            with self.subTest(program_rc=program_rc):
                run, events, status, lock_exists = self.run_cleanup(program_rc, sync_rc=9)
                self.assertEqual(run.returncode, expected_rc, run.stderr)
                self.assertIn('RUNNER_CLEANUP_SYNC_FAILED', run.stderr)
                self.assertEqual(status, f'RUNNER_EXIT={program_rc}\n')
                self.assertEqual(events, ['program-complete', 'rm', 'rmdir', 'sync', 'marker'])
                self.assertFalse(lock_exists)

    def test_source_is_valid_bash_without_running_its_top_level(self):
        subprocess.run(['bash', '-n', str(SOURCE)], check=True, capture_output=True, timeout=10)
        self.assertNotIn('HOME=', SOURCE.read_text())


if __name__ == '__main__':
    unittest.main()
