#!/usr/bin/env python3
"""Check launcher environment/quoting without starting Vivado or a board run.

The real launcher's start branch runs in a temporary Git repository with a
stub readiness check and capturing tmux command. Its assembled worker command
then runs a harmless environment reporter, including through an isolated
already-running tmux server when tmux is installed.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid


KEYS = ('ZP_REPO_DIR', 'ZP_FPGA_SEED_REPO_DIR', 'ZP_FPGA_LOG_ROOT', 'FPGA_CFG',
        'FPGA_VIVADO_THREADS', 'FPGA_NUM_THREADS', 'FPGA_NUM_CONTEXTS')
SOURCE = Path(__file__).with_name('launch_synthesis.sh')


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bp launcher 'quoted' ")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.env = os.environ.copy()
        for key in KEYS + ('TMUX', 'MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES'):
            self.env.pop(key, None)
        self.env.update(GIT_AUTHOR_NAME='Launcher Test', GIT_COMMITTER_NAME='Launcher Test',
                        GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_EMAIL='test@example.invalid')
        self.run_command(['git', 'init', '-q', str(self.repo)])
        self.run_command(['git', '-C', str(self.repo), 'commit', '-q', '--allow-empty', '-m', 'fixture'])
        self.commit = self.run_command(['git', '-C', str(self.repo), 'rev-parse', 'HEAD']).stdout.strip()
        self.launcher = self.repo / 'launch_synthesis.sh'
        shutil.copy2(SOURCE, self.launcher)
        self.launcher.chmod(0o755)
        ready = self.repo / 'check_build_ready.sh'
        ready.write_text('#!/bin/sh\nexit 0\n')
        ready.chmod(0o755)
        self.seed = self.base / 'seed "quoted"'
        self.seed.mkdir()
        self.logs = self.base / 'logs with spaces'
        self.capture = self.base / 'tmux-command.json'
        fake_bin = self.base / 'fake-bin'
        fake_bin.mkdir()
        fake_tmux = fake_bin / 'tmux'
        fake_tmux.write_text(
            '#!' + sys.executable + '\nimport json,os,pathlib,sys\n'
            'if sys.argv[1] == "new-session":\n'
            ' pathlib.Path(os.environ["LAUNCH_CAPTURE"]).write_text(json.dumps(sys.argv[1:]))\n'
            'elif sys.argv[1] == "display-message": print(os.getppid())\n'
            'else: raise SystemExit("unexpected tmux command")\n')
        fake_tmux.chmod(0o755)
        self.env.update(ZP_REPO_DIR=str(self.repo), ZP_FPGA_SEED_REPO_DIR=str(self.seed),
                        ZP_FPGA_LOG_ROOT=str(self.logs), FPGA_VIVADO_THREADS='7',
                        LAUNCH_CAPTURE=str(self.capture), PATH=str(fake_bin) + os.pathsep + self.env['PATH'])

    def run_command(self, command, **kwargs):
        return subprocess.run(command, env=kwargs.pop('env', self.env), check=True,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=10, **kwargs)

    def prepare_worker(self, custom=True):
        if custom:
            self.env.update(FPGA_CFG="cfg space 'quote' \"double\" $(false) `false`\nnext line",
                            FPGA_NUM_THREADS='2', FPGA_NUM_CONTEXTS='4')
        self.run_command([str(self.launcher), 'start'])
        captured = json.loads(self.capture.read_text())
        self.assertEqual(captured[:3], ['new-session', '-d', '-s'])
        command = captured[-1]
        self.job_dir, = self.logs.iterdir()
        self.console = self.job_dir / 'console.log'
        # Replace only the temporary copy after capturing real command assembly.
        # Executing this worker can never enter the real synthesis worker branch.
        self.launcher.write_text(
            '#!' + sys.executable + '\nimport json,os,signal,sys\n'
            'print(json.dumps({"environment":{k:os.environ.get(k) for k in '
            + repr(KEYS) + '},"args":sys.argv[1:],'
            '"ignores_hup":signal.getsignal(signal.SIGHUP)==signal.SIG_IGN}))\n')
        return command

    def assert_worker(self, custom=True):
        result = json.loads(self.console.read_text())
        expected = {key: self.env.get(key, '') for key in KEYS}
        if not custom:
            expected['FPGA_CFG'] = 'e_bp_unicore_zynqparrot_cfg'
        self.assertEqual(result['environment'], expected)
        self.assertEqual(result['args'], ['worker', self.job_dir.name, self.commit])
        self.assertTrue(result['ignores_hup'])

    def test_real_command_round_trips_values_through_posix_shell(self):
        command = self.prepare_worker()
        stale = dict(self.env, **{key: 'old-server-value' for key in KEYS})
        self.run_command(['/bin/sh', '-c', command], env=stale)
        self.assert_worker()

    def test_resolved_defaults_override_stale_server_values(self):
        command = self.prepare_worker(custom=False)
        stale = dict(self.env, **{key: 'old-server-value' for key in KEYS})
        self.run_command(['/bin/sh', '-c', command], env=stale)
        self.assert_worker(custom=False)

    @unittest.skipUnless(shutil.which('tmux'), 'tmux is not installed')
    def test_existing_isolated_tmux_server_receives_explicit_values(self):
        command = self.prepare_worker()
        # Resolve the real executable outside the capturing PATH fixture.
        tmux = [shutil.which('tmux'), '-L', 'bp-launch-test-' + uuid.uuid4().hex, '-f', '/dev/null']
        stale = dict(self.env, **{key: 'old-server-value' for key in KEYS})
        try:
            self.run_command(tmux + ['new-session', '-d', '-s', 'seed', 'cat'], env=stale)
            self.run_command(tmux + ['new-session', '-d', '-s', 'worker', command])
            deadline = time.monotonic() + 5
            while True:
                try:
                    json.loads(self.console.read_text())
                    break
                except (FileNotFoundError, json.JSONDecodeError):
                    if time.monotonic() >= deadline:
                        self.fail('isolated tmux worker did not produce its report')
                    time.sleep(0.01)
            self.assert_worker()
        finally:
            subprocess.run(tmux + ['kill-server'], env=stale, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5)


if __name__ == '__main__':
    unittest.main()
