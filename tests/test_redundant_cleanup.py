#!/usr/bin/env python3
"""Execute removed cleanup against real temporary trees and isolated sysctls."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RedundantCleanup(unittest.TestCase):
    def test_build_tree_cleanup(self):
        workflow = (ROOT / '.github/workflows/W1700K.yaml').read_text()
        start = workflow.index('          mountpoint $DK_BIN')
        end = workflow.index('          ln -s $DK_BIN', start)
        current = workflow[start:end]
        previous = ('rm -f build_dir/target-*/linux-*/.prepared* '
                    'build_dir/target-*/linux-*/.config*\n' + current)
        for populated in (False, True):
            results = []
            for script in (previous, current):
                with tempfile.TemporaryDirectory() as tmp:
                    tree = Path(tmp)
                    (tree / 'keep').write_text('preserved')
                    if populated:
                        for name in ('build_dir/target-a/linux-a/.prepared_1',
                                     'build_dir/target-b/linux-b/.config',
                                     'build_dir/target-a/linux-a/object.o',
                                     'staging_dir/tool', 'bin/image', 'dl/archive'):
                            path = tree / name
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_text('fixture')
                    result = subprocess.run(['bash', '-e', '-c',
                                             'mountpoint() { return 0; };\n' + script],
                                            cwd=tree, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    results.append(sorted(str(p.relative_to(tree)) for p in tree.rglob('*')))
            self.assertEqual(results, [['keep'], ['keep']])

    def test_sysctl_load_order(self):
        # BusyBox sysctl uses /proc/sys relative to a chroot. Copy its runtime
        # dependencies so the actual parser writes only into our fake proc tree.
        import shutil
        import re
        binary = shutil.which('busybox')
        assert binary, 'BusyBox is required'
        busybox = Path(binary)
        libraries = re.findall(r'(/[^\s()]+)', subprocess.check_output(
            ['ldd', str(busybox)], text=True))
        config = ROOT / 'user/default/files/etc/sysctl.d'
        states = []
        for restore_duplicate in (True, False):
            with tempfile.TemporaryDirectory() as tmp:
                jail = Path(tmp)
                for source in [str(busybox), *libraries]:
                    target = jail / source.lstrip('/')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                files = []
                for source in sorted(config.glob('*.conf')):
                    text = source.read_text()
                    if restore_duplicate and source.name == '12-apmode-offload.conf':
                        text += 'net.bridge.bridge-nf-filter-vlan-tagged=1\n'
                    target = jail / source.name
                    target.write_text(text)
                    files.append('/' + source.name)
                    for line in text.splitlines():
                        if '=' in line and not line.lstrip().startswith('#'):
                            key = line.split('=', 1)[0].strip()
                            node = jail / 'proc/sys' / key.replace('.', '/')
                            node.parent.mkdir(parents=True, exist_ok=True)
                            node.write_text('0\n')
                for name in files:
                    result = subprocess.run(['chroot', tmp, str(busybox), 'sysctl', '-p', name],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                states.append({str(p.relative_to(jail / 'proc/sys')): p.read_text()
                               for p in (jail / 'proc/sys').rglob('*') if p.is_file()})
        self.assertEqual(states[0], states[1])
        self.assertEqual(states[1]['net/bridge/bridge-nf-filter-vlan-tagged'].strip(), '1')


if __name__ == '__main__':
    unittest.main()
