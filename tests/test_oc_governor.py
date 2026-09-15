#!/usr/bin/env python3
"""Run the actual OC block, never the full customization script.

Optional real-source merge: set IMMORTALWRT_SOURCE to a prepared source tree
(with scripts/kconfig.pl and target/linux/generic/config-6.18).
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'user/default'
CUSTOM = (PROFILE / 'custom.sh').read_text()
START = CUSTOM.index("if grep -q '^CONFIG_CPU_FREQ_DEFAULT_GOV_PERFORMANCE=y'")
BLOCK = CUSTOM[START:CUSTOM.index('\n# -------------------------------------------------', START)]
CONFIG = Path('target/linux/airoha/an7581/config-6.18')
DTS = Path('target/linux/airoha/dts/an7581.dtsi')
PLL = Path('target/linux/airoha/patches-6.18/940-pmdomain-airoha-Add-Airoha-CPU-PM-Domain-support.patch')
BASE = ('CONFIG_CPU_FREQ=y\nCONFIG_CPU_FREQ_DEFAULT_GOV_ONDEMAND=y\n'
        '# CONFIG_CPU_FREQ_DEFAULT_GOV_PERFORMANCE is not set\n'
        'CONFIG_CPU_FREQ_GOV_ONDEMAND=y\nCONFIG_CPU_FREQ_GOV_PERFORMANCE=y\n')


class OCGovernor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tree = Path(self.temp.name)
        # Reconstruct the real OPP patch's preimage, not a mocked patch command.
        patch = (PROFILE / 'patches/001-oc-cpu-opp-1400mhz.patch').read_text()
        hunk = patch[patch.index('@@'):].splitlines()[1:]
        preimage = '\n'.join(line[1:] for line in hunk if line.startswith((' ', '-'))) + '\n'
        for path, text in ((CONFIG, BASE), (DTS, preimage),
                           (PLL, '+\tunsigned int freq_mhz = 500 + state * 50;\n')):
            (self.tree / path).parent.mkdir(parents=True, exist_ok=True)
            (self.tree / path).write_text(text)

    def run_block(self, enabled=True):
        (self.tree / '.config').write_text('CONFIG_CPU_FREQ_DEFAULT_GOV_PERFORMANCE=y\n' if enabled else '')
        return subprocess.run(['bash', '-ec', BLOCK], cwd=self.tree,
                              env=dict(os.environ, DK_PROFILE=str(PROFILE)),
                              text=True, capture_output=True)

    def assert_governor(self, text, governor):
        self.assertEqual(re.findall(r'^CONFIG_CPU_FREQ_DEFAULT_GOV_\w+=y$', text, re.M),
                         [f'CONFIG_CPU_FREQ_DEFAULT_GOV_{governor}=y'])
        other = 'ONDEMAND' if governor == 'PERFORMANCE' else 'PERFORMANCE'
        self.assertIn(f'# CONFIG_CPU_FREQ_DEFAULT_GOV_{other} is not set', text)

    def test_oc_performance_and_opp_pll(self):
        result = self.run_block()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_governor((self.tree / CONFIG).read_text(), 'PERFORMANCE')
        self.assertIn('700 + state * 50', (self.tree / PLL).read_text())
        states = re.findall(r'opp-hz = /bits/ 64 <(\d+)>;\s*required-opps = <&smcc_opp(\d+)>;',
                            (self.tree / DTS).read_text())
        self.assertEqual(len(states), 15)
        for hz, state in states:
            self.assertEqual(int(hz), (700 + int(state) * 50) * 1000000)

    def test_standard_unchanged(self):
        before = {path: (self.tree / path).read_bytes() for path in (CONFIG, DTS, PLL)}
        result = self.run_block(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, data in before.items():
            self.assertEqual((self.tree / path).read_bytes(), data)
        self.assert_governor((self.tree / CONFIG).read_text(), 'ONDEMAND')

    def test_missing_or_changed_governor_baseline_aborts(self):
        for text in (None, BASE.replace('ONDEMAND=y', 'SCHEDUTIL=y'),
                     BASE.replace('# CONFIG_CPU_FREQ_DEFAULT_GOV_PERFORMANCE is not set\n', '')):
            with self.subTest(config=text):
                path = self.tree / CONFIG
                if text is None:
                    path.unlink()
                else:
                    path.write_text(text)
                before = (self.tree / DTS).read_bytes()
                result = self.run_block()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('unexpected CPU governor baseline', result.stderr)
                self.assertEqual((self.tree / DTS).read_bytes(), before)

    def test_other_default_disabled(self):
        (self.tree / CONFIG).write_text(BASE + 'CONFIG_CPU_FREQ_DEFAULT_GOV_SCHEDUTIL=y\n')
        result = self.run_block()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_governor((self.tree / CONFIG).read_text(), 'PERFORMANCE')
        self.assertIn('# CONFIG_CPU_FREQ_DEFAULT_GOV_SCHEDUTIL is not set',
                      (self.tree / CONFIG).read_text())

    @unittest.skipUnless(os.environ.get('IMMORTALWRT_SOURCE'),
                         'set IMMORTALWRT_SOURCE for real kernel config merge')
    def test_real_kernel_config_merge(self):
        source = Path(os.environ['IMMORTALWRT_SOURCE'])
        original = (source / CONFIG).read_text()
        generic = source / 'target/linux/generic/config-6.18'
        kconfig = source / 'scripts/kconfig.pl'
        # This target has no parent fragment; include one if upstream adds it.
        parent = source / 'target/linux/airoha'
        target = next((p for p in (parent / 'config-6.18', parent / 'config-default')
                       if p.is_file()), None)
        inputs = [generic] + ([target] if target else []) + [self.tree / CONFIG]
        for enabled, governor in ((False, 'ONDEMAND'), (True, 'PERFORMANCE')):
            with self.subTest(governor=governor):
                (self.tree / CONFIG).write_text(original)
                result = self.run_block(enabled)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                merged = subprocess.run(['perl', str(kconfig)] + ['+'] * (len(inputs) - 1)
                                        + list(map(str, inputs)), check=True,
                                        text=True, capture_output=True)
                self.assertEqual(merged.stderr, '')
                self.assert_governor(merged.stdout, governor)


if __name__ == '__main__':
    unittest.main()
