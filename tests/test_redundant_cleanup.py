#!/usr/bin/env python3
"""Execute removed cleanup against real temporary trees and isolated sysctls."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RedundantCleanup(unittest.TestCase):
    def test_build_tree_cleanup(self):
        workflow = (ROOT / '.github/workflows/W1700K.yaml').read_text()
        start = workflow.index('          git clean -ffdx')
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
                    subprocess.run(['git', 'init', '-q', str(tree)], check=True)
                    subprocess.run(['git', '-C', str(tree), 'add', 'keep'], check=True)
                    if populated:
                        for name in ('build_dir/target-a/linux-a/.prepared_1',
                                     'build_dir/target-b/linux-b/.config',
                                     'build_dir/target-a/linux-a/object.o',
                                     'staging_dir/tool', 'bin/image', 'dl/archive'):
                            path = tree / name
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_text('fixture')
                        (tree / 'files').mkdir()
                        (tree / 'files/build_info').write_text('preseeded donor metadata')
                        (tree / '.gitignore').write_text('files/\n')
                        subprocess.run(['git', '-C', str(tree), 'add', '.gitignore'], check=True)
                    result = subprocess.run(['bash', '-e', '-c',
                                             'mountpoint() { return 0; };\n' + script],
                                            cwd=tree, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    results.append(sorted(str(p.relative_to(tree)) for p in tree.rglob('*')
                                          if '.git' not in p.relative_to(tree).parts))
            expected = ['.gitignore', 'keep'] if populated else ['keep']
            self.assertEqual(results, [expected, expected])

    def test_sysctl_load_order(self):
        # BusyBox sysctl uses /proc/sys relative to a chroot. Copy its runtime
        # dependencies so the actual parser writes only into our fake proc tree.
        import shutil
        import re
        binary = shutil.which('busybox')
        assert binary, 'BusyBox is required'
        chroot = shutil.which('chroot', path=os.pathsep.join((os.environ.get('PATH', ''), '/usr/sbin', '/sbin')))
        assert chroot, 'chroot is required'
        busybox = Path(binary)
        libraries = re.findall(r'(/[^\s()]+)', subprocess.check_output(
            ['ldd', str(busybox)], text=True))
        config = ROOT / 'user/default/files/etc/sysctl.d'
        # Removed filter toggles must remain whatever the operator/kernel supplied.
        # The remaining call_* and pass-vlan-input-dev settings still load normally.
        for initial in ('0', '1'):
            with self.subTest(initial=initial), tempfile.TemporaryDirectory() as tmp:
                jail = Path(tmp)
                for source in [str(busybox), *libraries]:
                    target = jail / source.lstrip('/')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                filters = ('bridge-nf-filter-vlan-tagged', 'bridge-nf-filter-pppoe-tagged')
                for key in filters:
                    node = jail / 'proc/sys/net/bridge' / key
                    node.parent.mkdir(parents=True, exist_ok=True)
                    node.write_text(initial + '\n')
                files = []
                for source in sorted(config.glob('*.conf')):
                    text = source.read_text()
                    target = jail / source.name
                    target.write_text(text)
                    files.append('/' + source.name)
                    for line in text.splitlines():
                        if '=' in line and not line.lstrip().startswith('#'):
                            key = line.split('=', 1)[0].strip()
                            node = jail / 'proc/sys' / key.replace('.', '/')
                            node.parent.mkdir(parents=True, exist_ok=True)
                            if not node.exists():
                                node.write_text('9\n')
                for name in files:
                    result = subprocess.run([chroot, tmp, str(busybox), 'sysctl', '-p', name],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                bridge = jail / 'proc/sys/net/bridge'
                for key in filters:
                    self.assertEqual((bridge / key).read_text().strip(), initial)
                for family in ('iptables', 'ip6tables', 'arptables'):
                    self.assertEqual((bridge / ('bridge-nf-call-' + family)).read_text().strip(), '0')
                self.assertEqual((bridge / 'bridge-nf-pass-vlan-input-dev').read_text().strip(), '1')


if __name__ == '__main__':
    unittest.main()
