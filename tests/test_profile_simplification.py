"""Authorized profile pruning; prepared assertions use real native defconfig."""
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'user/default'
LUCI_DEPENDENCIES = (
    'luci-base', 'luci-light', 'luci-mod-admin-full', 'luci-mod-network',
    'luci-mod-status', 'luci-mod-system', 'luci-proto-ipv6', 'luci-proto-ppp',
    'luci-theme-bootstrap', 'luci-app-firewall', 'luci-app-package-manager',
)


class ProfileSimplification(unittest.TestCase):
    def test_luci_dependencies_owned_by_metapackage(self):
        config = (PROFILE / 'config.diff').read_text().splitlines()
        self.assertIn('CONFIG_PACKAGE_luci=y', config)
        for package in LUCI_DEPENDENCIES:
            self.assertNotIn(f'CONFIG_PACKAGE_{package}=y', config)

    def test_retired_phy_group_absent(self):
        self.assertFalse((PROFILE / 'tree').exists())
        self.assertFalse((PROFILE / 'patches/999-net-phy-realtek-rtl8261ce.patch').exists())
        for name in ('custom.sh', 'config.diff'):
            self.assertNotIn('rtl8261ce', (PROFILE / name).read_text().lower())
        self.assertNotIn('尚无完整 CE 替代', (PROFILE / 'patches/README.md').read_text())
        self.assertTrue((PROFILE / 'patches/998-single-wiphy.patch').is_file())

    @unittest.skipUnless(os.environ.get('IMMORTALWRT_SOURCE'), 'requires prepared official source')
    def test_prepared_official_closure(self):
        source = Path(os.environ['IMMORTALWRT_SOURCE'])
        config = (source / '.config').read_text()
        for package in (*LUCI_DEPENDENCIES, 'kmod-phy-realtek',
                        'rtl8261c-firmware', 'rtl826x-firmware', 'kmod-tcp-bbr'):
            self.assertIn(f'CONFIG_PACKAGE_{package}=y', config.splitlines())
        self.assertNotIn('rtl8261ce', config)
        self.assertNotIn('CONFIG_PACKAGE_kmod-sched=y', config)
        self.assertFalse((source / 'files/etc/sysctl.d/10-bbr.conf').exists())
        self.assertFalse((source / 'target/linux/generic/files/drivers/net/phy/rtl8261ce').exists())
        self.assertFalse((source / 'target/linux/generic/hack-6.18/999-net-phy-realtek-rtl8261ce.patch').exists())
        import subprocess
        for name in ('package/kernel/linux/modules/netdevices.mk',
                     'package/firmware/linux-firmware/realtek.mk',
                     'package/firmware/rtl826x-firmware/Makefile',
                     'target/linux/airoha/image/an7581.mk'):
            self.assertEqual((source / name).read_bytes(), subprocess.check_output(
                ['git', 'show', 'HEAD:' + name], cwd=source), name)

    def test_no_unimplemented_fq_override(self):
        self.assertFalse((PROFILE / 'files/etc/sysctl.d/10-bbr.conf').exists())
        self.assertIn('CONFIG_PACKAGE_kmod-tcp-bbr=y',
                      (PROFILE / 'config.diff').read_text().splitlines())
        for path in (PROFILE / 'files/etc/sysctl.d').glob('*.conf'):
            self.assertNotIn('net.core.default_qdisc=fq', path.read_text())


if __name__ == '__main__':
    unittest.main()
