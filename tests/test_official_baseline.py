"""Official baseline and retained-upgrade cleanup, with isolated I/O only."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_cache_workflow import ROOT, step
import test_release_safety as releases
from patch_source import PATCHES


class OfficialBaselineTests(unittest.TestCase):
    def test_clean_official_source_and_single_variant(self):
        workflow = (ROOT / '.github/workflows/W1700K.yaml').read_text()
        self.assertNotIn('matrix.', workflow)
        self.assertNotIn('ubi2-oc', workflow)
        self.assertIn("cron: '0 4 * * *'", workflow)
        block = step('inputs')['run']
        self.assertNotIn('cp -f $DK_PROFILE/feeds.conf', block)
        self.assertNotIn('> version', block)
        custom = (ROOT / 'user/default/custom.sh').read_text()
        self.assertNotIn('OpenWRT-fanboy', custom)
        self.assertNotIn('CPU_FREQ', custom)
        self.assertNotIn('bridge-flowtable', custom)
        overlay = PATCHES / 'tree/target/linux/airoha/patches-6.18'
        self.assertTrue(list(overlay.glob('745-net-pcs-*.patch')))
        self.assertTrue(list(overlay.glob('746-net-dsa-*.patch')))

    def test_only_mt76_refresh_delta_is_retained(self):
        patches = PATCHES / 'patches'
        custom = (ROOT / 'user/default/custom.sh').read_text()
        self.assertFalse(list(patches.glob('910-mt76-*.patch')))
        self.assertNotIn('910-mt76-', custom)
        overlay = PATCHES / 'tree/package/kernel/mt76/patches'
        self.assertFalse(list(overlay.glob('910-mt76-*.patch')))
        self.assertTrue((overlay / '911-mt76-mt7996-refresh-power-limits-on-txpower-changes.patch').is_file())
        # Upstream owns pending cancellation; keep independent per-BSS power logic.
        power = (patches / '920-wifi-non-mlo-ap-txpower.patch').read_text()
        self.assertNotIn('+\t\tpending.abort();', power)
        self.assertIn('+function bss_txpower(', power)

    def test_retained_cleanup_is_idempotent(self):
        script = (ROOT / 'user/default/files/etc/uci-defaults/90-bridge-hw-offload').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            paths = ['/usr/share/bridge-flow-offload/apply-rules.sh',
                     '/etc/hotplug.d/iface/51-bridge-flow-offload',
                     '/etc/hotplug.d/iface/51-bridge-hw-offload',
                     '/etc/hotplug.d/net/50-bridge-hw-offload',
                     '/usr/share/nftables.d/ruleset-post/30-bridge-offload.nft']
            for path in paths:
                p = base / path.lstrip('/')
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('obsolete')
                script = script.replace(path, str(p))
            for _ in range(2):
                # Production script has no errexit: absent UCI section is benign.
                result = subprocess.run(['sh', '-c', 'uci() { return 1; };\n' + script])
                self.assertEqual(result.returncode, 0)
                self.assertTrue(all(not (base / p.lstrip('/')).exists() for p in paths))

    def test_missing_each_application_or_translation_blocks_release(self):
        helper = releases.ReleaseTests()
        for app in ('airoha-fancontrol', 'airoha-flowsense', 'airoha-npu', 'wifi7', 'wol', 'ttyd'):
            for pkg in ('luci-app-' + app, 'luci-i18n-' + app + '-zh-cn'):
                with self.subTest(package=pkg), tempfile.TemporaryDirectory() as tmp:
                    base = Path(tmp)
                    helper.fixture(base)
                    (base / '.config').write_text(releases.CONFIG.replace('CONFIG_PACKAGE_' + pkg + '=y\n', ''))
                    result = helper.stage(base)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('required application', result.stderr)
