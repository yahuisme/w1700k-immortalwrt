"""Exercise revision logging with real local Git repositories; no network."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_cache_workflow import render, step


class RevisionLogTests(unittest.TestCase):
    def test_actual_checkout_revisions(self):
        block = step('Prepare source and toolchain cache key')['run']
        self.assertIn('# Log actual input revisions', block)
        block = block.split('# Log actual input revisions', 1)[1].split('\n', 1)[1].split('make defconfig', 1)[0]
        paths = ['.', 'feeds/luci', 'feeds/packages', '/tmp/openw1700k',
                 '/tmp/yahuisme-packages', 'package/luci-theme-aurora',
                 'package/luci-app-aurora-config']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = {}
            for index, path in enumerate(paths):
                local = root / (path.lstrip('/') if path.startswith('/') else path)
                local.mkdir(parents=True, exist_ok=True)
                def git(*args):
                    return subprocess.check_output(['git', '-C', str(local), *args], stderr=subprocess.DEVNULL, text=True).strip()
                git('init')
                git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    'commit', '--allow-empty', '-m', f'input {index}')
                expected[path] = git('rev-parse', 'HEAD')
            block = block.replace('/tmp/openw1700k', str(root / 'tmp/openw1700k'))
            block = block.replace('/tmp/yahuisme-packages', str(root / 'tmp/yahuisme-packages'))
            result = subprocess.run(['bash', '-e', '-c', render(block, {})], cwd=root,
                                    env=dict(os.environ, REPO_BRANCH='master'), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for sha in expected.values():
                self.assertEqual(result.stdout.count(sha), 1, result.stdout)
            self.assertIn('Source ImmortalWrt/master:', result.stdout)
            self.assertIn('Donor OpenW1700k/ubi2:', result.stdout)
            self.assertEqual(len(result.stdout.splitlines()), len(paths))
            self.assertEqual(list(root.glob('*.lock')), [])
