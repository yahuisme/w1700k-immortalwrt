"""Official baseline and retained-upgrade cleanup, with isolated I/O only."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_cache_workflow import ROOT, step
import test_release_safety as releases


class OfficialBaselineTests(unittest.TestCase):
    def test_clean_official_source_and_single_variant(self):
        workflow = (ROOT / '.github/workflows/W1700K.yaml').read_text()
        self.assertNotIn('matrix.', workflow)
        self.assertNotIn('ubi2-oc', workflow)
        self.assertIn("cron: '0 4 * * *'", workflow)
        block = step('inputs')['run']
        self.assertLess(block.index('git clean -ffdx'), block.index('cp -f $DK_PROFILE/feeds.conf'))
        self.assertNotIn('> version', block)
        custom = (ROOT / 'user/default/custom.sh').read_text()
        self.assertNotIn('OpenWRT-fanboy', custom)
        self.assertNotIn('CPU_FREQ', custom)
        self.assertNotIn('bridge-flowtable', custom)
        self.assertIn('745-net-pcs', custom)
        self.assertIn('746-net-dsa', custom)

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
