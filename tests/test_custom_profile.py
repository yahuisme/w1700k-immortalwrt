#!/usr/bin/env python3
"""Exercise production Aurora install/preset shell and package boundaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CUSTOM = (ROOT / 'user/default/custom.sh').read_text()


class CustomProfile(unittest.TestCase):
    def test_explicit_packages_keep_driver_injection(self):
        config = (ROOT / 'user/default/config.diff').read_text().splitlines()
        for package in ('bridge-hw-offload', 'kmod-crypto-hw-eip93', 'kmod-phy-rtl8261ce'):
            self.assertIn(f'CONFIG_PACKAGE_{package}=y', config)
        self.assertNotIn('TMK=', CUSTOM)
        self.assertNotIn('ANM=', CUSTOM)
        self.assertIn('define KernelPackage/phy-rtl8261ce', CUSTOM)
        self.assertIn('999-net-phy-realtek-rtl8261ce.patch', CUSTOM)
        self.assertIn('rtl8261ce/Kconfig', CUSTOM)

    def test_complete_aurora_fragment(self):
        start = CUSTOM.index('echo "Installing latest Aurora')
        end = CUSTOM.index('# Add Chinese translations', start)
        fragment = CUSTOM[start:end]
        # Only git is mocked: execute both complete installs, Makefile guards,
        # template edits and failure propagation on isolated disk fixtures.
        mock = '''git() {
    local dest="${@: -1}"
    mkdir -p "$dest"
    [ "$MODE" = missing-makefile ] || touch "$dest/Makefile"
    if [[ "$dest" = *luci-app-aurora-config ]]; then
        local dir="$dest/root/usr/share/aurora"
        [ "$MODE" != missing-dir ] || return 0
        mkdir -p "$dir"
        [ "$MODE" != empty-dir ] || return 0
        for name in default custom; do
            [ "$MODE:$name" != missing-default:default ] || continue
            printf "\\toption nav_type 'mega-menu'  \\n\\toption struct_radius_base '0.5rem' \\n" > "$dir/$name.template"
        done
        if [ "$MODE" = mismatch ]; then
            printf "option unknown 'upstream-changed'\\n" > "$dir/custom.template"
        fi
    fi
}
'''
        for mode in ('success', 'missing-makefile', 'missing-dir', 'empty-dir',
                     'missing-default', 'mismatch'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                result = subprocess.run(['bash', '-ec', mock + fragment + '\ntouch reached'],
                                        cwd=tmp, env=dict(os.environ, MODE=mode),
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode == 0, mode == 'success', result.stdout + result.stderr)
                self.assertEqual((Path(tmp) / 'reached').exists(), mode == 'success')
                if mode == 'success':
                    for tpl in Path(tmp).rglob('*.template'):
                        self.assertIn("option nav_type 'sidebar'", tpl.read_text())
                        self.assertIn("option struct_radius_base '0.125rem'", tpl.read_text())


if __name__ == '__main__':
    unittest.main()
