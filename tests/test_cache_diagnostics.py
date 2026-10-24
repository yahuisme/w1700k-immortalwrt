"""Diagnostics do not change the CURRENT generation compatibility policy."""
import contextlib
import importlib.util
import inspect
import io
import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/cache.py'
# Baseline is generated from current policy below; legacy digests are retired.


def load(path):
    spec = importlib.util.spec_from_file_location('cache_diagnostics_under_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, DK_PROFILE=str(SCRIPT.parents[1] / 'user/default')):
        spec.loader.exec_module(module)
    return module


class CacheDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'source'
        self.root.mkdir()
        self.cache = load(SCRIPT)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for name in self.cache.INPUTS:
            self.put(name + '/Makefile' if name in self.cache.INPUTS[:7] else name,
                     'input\n')
        self.put('.config', 'CONFIG_PACKAGE_fixture=y\n# private-config-marker\n')

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def invoke(self, module=None, builder='fixed-builder', machine='fixed-aarch64'):
        module = module or self.cache
        out, err = io.StringIO(), io.StringIO()
        uname = type('FixedUname', (), {'machine': machine})()
        with patch.object(module.os, 'uname', return_value=uname), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            value = module.key(self.root, builder)
        self.assertEqual(out.getvalue(), '')
        return value, err.getvalue()

    def groups(self, stderr):
        lines = stderr.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('cache-inputs sha256/16 '), stderr)
        values = dict(token.split('=', 1) for token in lines[0].split()[2:])
        self.assertEqual(list(values), ['environment', *self.cache.INPUTS])
        for group, value in values.items():
            self.assertRegex(value, r'^[0-9a-f]{16}$', group)
        return values

    def test_one_line_diagnostics_use_existing_serialized_bytes(self):
        value, stderr = self.invoke()
        self.assertRegex(value, r'^[0-9a-f]{64}$')
        groups = self.groups(stderr)
        self.assertNotIn('private-config-marker', stderr)
        expected = hashlib.sha256(json.dumps([
            '.config', (self.root / '.config').stat().st_mode,
            hashlib.sha256((self.root / '.config').read_bytes()).hexdigest()
        ]).encode()).hexdigest()[:16]
        self.assertEqual(groups['.config'], expected)

    def test_group_changes_isolate_content_mode_config_and_environment(self):
        before, stderr = self.invoke()
        groups = self.groups(stderr)
        for name, text, changed in (
                ('tools/Makefile', 'changed\n', 'tools'),
                ('.config', 'CONFIG_PACKAGE_fixture=m\n', '.config')):
            p = self.root / name
            old = p.read_text()
            p.write_text(text)
            after, stderr = self.invoke()
            self.assertNotEqual(before, after)
            self.assertEqual([k for k, v in self.groups(stderr).items() if v != groups[k]], [changed])
            p.write_text(old)
        p = self.root / 'tools/Makefile'
        mode = p.stat().st_mode
        p.chmod(mode ^ 0o100)
        after, stderr = self.invoke()
        self.assertNotEqual(before, after)
        self.assertEqual([k for k, v in self.groups(stderr).items() if v != groups[k]], ['tools'])
        p.chmod(mode)
        for kwargs in ({'builder': 'changed-builder'}, {'machine': 'other-host'}):
            after, stderr = self.invoke(**kwargs)
            self.assertNotEqual(before, after)
            self.assertEqual([k for k, v in self.groups(stderr).items() if v != groups[k]], ['environment'])

    def test_generated_files_and_mtimes_remain_outside_key(self):
        self.put('scripts/config/.gitignore', 'conf\n*.o\n')
        before = self.invoke()
        output = self.put('scripts/config/conf', 'generated')
        completed = self.put('build_dir/host/complete', 'stamp')
        stamp = 1700000000123456789
        os.utime(completed, ns=(stamp, stamp))
        os.utime(output, ns=(stamp, stamp))
        (self.root / 'tools/Makefile').touch()
        self.assertEqual(before, self.invoke())
        self.assertEqual(completed.stat().st_mtime_ns, stamp)
        self.assertEqual(output.stat().st_mtime_ns, stamp)
        self.assertEqual((self.root / 'tools/Makefile').stat().st_mtime_ns,
                         self.cache.EPOCH * 1_000_000_000)
        output.write_text('changed generated output')
        self.assertEqual(before, self.invoke())

    def test_cli_stdout_remains_only_full_key_and_stdin_is_unused(self):
        env = dict(os.environ, DK_PROFILE=str(SCRIPT.parents[1] / 'user/default'))
        result = subprocess.run([sys.executable, str(SCRIPT), 'key', str(self.root),
                                 str(self.root / 'unused-cache'), 'fixed-builder'],
                                env=env, input='ignored stdin secret', text=True,
                                capture_output=True, check=True)
        self.assertRegex(result.stdout, r'^[0-9a-f]{64}\n$')
        self.groups(result.stderr)
        self.assertNotIn('ignored stdin secret', result.stderr)

    def test_current_policy_without_diagnostics_same_source_reads_order_and_mtimes(self):
        # Compare current policy without diagnostics, not a retired generation.
        # Strip only marked diagnostic lines from this exact current policy.
        baseline = Path(self.tmp.name) / 'current_policy_no_diagnostics.py'
        baseline.write_text(''.join(line for line in SCRIPT.read_text().splitlines(keepends=True)
                                    if not line.endswith('  # cache diagnostic\n')))
        legacy = load(baseline)
        # Both implementations lock the shared helper and current policy.
        self.assertEqual(self.cache.key_policy_source(), inspect.getsource(legacy.key))
        for change in ('unchanged', 'content', 'mode', 'config', 'builder', 'host', 'generated', 'mtime'):
            with self.subTest(change=change):
                builder, machine = 'fixed-builder', 'fixed-aarch64'
                if change == 'content':
                    self.put('tools/Makefile', 'new content')
                elif change == 'mode':
                    (self.root / 'tools/Makefile').chmod(0o755)
                elif change == 'config':
                    self.put('.config', 'CONFIG_PACKAGE_fixture=m\n')
                elif change == 'builder':
                    builder = 'changed-builder'
                elif change == 'host':
                    machine = 'other-host'
                elif change == 'generated':
                    self.put('scripts/config/.gitignore', 'conf\n')
                    self.put('scripts/config/conf', 'generated')
                elif change == 'mtime':
                    (self.root / 'tools/Makefile').touch()
                traces = []
                values = []
                for module in (legacy, self.cache):
                    trace = []
                    with contextlib.ExitStack() as stack:
                        for method in ('read_bytes', 'read_text', 'rglob'):
                            original = getattr(Path, method)
                            def tracked(path, *args, _original=original, _method=method, **kwargs):
                                # inspect reads module source itself, not fixture inputs.
                                if path.is_relative_to(self.root):
                                    trace.append((_method, str(path.relative_to(self.root)), args))
                                return _original(path, *args, **kwargs)
                            stack.enter_context(patch.object(Path, method, tracked))
                        values.append(self.invoke(module, builder, machine)[0])
                    traces.append(trace)
                    self.assertEqual((self.root / 'tools/Makefile').stat().st_mtime_ns,
                                     module.EPOCH * 1_000_000_000)
                self.assertEqual(values[0], values[1])
                self.assertEqual(traces[0], traces[1])


if __name__ == '__main__':
    unittest.main()
