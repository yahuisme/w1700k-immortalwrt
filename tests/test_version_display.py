"""Render real official templates; full custom preservation is tested separately.

VERSION_SOURCE=/path/to/fixed/upstream python3 tests/test_version_display.py
No compilation or defconfig; make executes only the upstream version sed recipe.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


class VersionDisplay(unittest.TestCase):
    def test_official_snapshot_templates_and_machine_metadata(self):
        source = os.environ.get('VERSION_SOURCE')
        if not source:
            self.skipTest('set VERSION_SOURCE to real upstream templates')
        source = Path(source)
        install = re.search(r'\$\(VERSION_SED_SCRIPT\) \\\n(.*?)(?=\n\s*\n)',
                            (source / 'package/base-files/Makefile').read_text(), re.S)
        assert install is not None, 'upstream template install list changed'
        names = re.findall(r'\$\(1\)/(\S+)', install[1])
        qstrip = next(line for line in (source / 'rules.mk').read_text().splitlines()
                      if line.startswith('qstrip='))
        for revision in ('r41341-f44d1535b4', 'r12345-0123456789'):
            with self.subTest(revision=revision), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                shutil.copytree(source / 'package/base-files', root / 'package/base-files')
                shutil.copytree(source / 'include', root / 'include')
                version_mk = (root / 'include/version.mk').read_bytes()
                makefile = f'''empty:=
space:=$(empty) $(empty)
comma:=,
{qstrip}
tolower=$(shell printf '%s' '$(1)' | tr A-Z a-z)
SED:=sed -i -e
REVISION:={revision}
BOARD:=airoha
SUBTARGET:=an7581
ARCH_PACKAGES:=aarch64_cortex-a53
SOURCE_DATE_EPOCH:=1
include include/version.mk
all:
\t$(VERSION_SED_SCRIPT) {' '.join('package/base-files/files/' + name for name in names)}
\t@printf '%s\\n' '$(VERSION_NUMBER)' '$(VERSION_CODE)' '$(VERSION_REPO)' > metadata
'''
                (root / 'Makefile').write_text(makefile)
                subprocess.run(['make', '--no-print-directory'], cwd=root, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                base = root / 'package/base-files/files'
                self.assertEqual((root / 'include/version.mk').read_bytes(), version_mk)
                metadata = (root / 'metadata').read_text().splitlines()
                self.assertEqual(metadata[:2], ['SNAPSHOT', revision])
                self.assertTrue(metadata[2].endswith('/snapshots'))
                self.assertEqual((base / 'etc/openwrt_version').read_text(), revision + '\n')
                self.assertIn(' SNAPSHOT, ' + revision, (base / 'etc/banner').read_text())
                self.assertIn("DISTRIB_REVISION='" + revision + "'", (base / 'etc/openwrt_release').read_text())
                self.assertIn('BUILD_ID="' + revision + '"', (base / 'usr/lib/os-release').read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
