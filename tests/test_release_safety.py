"""Execute complete stage/publish shell blocks, real files and local gh stub only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_cache_workflow import ROOT, render, step
import test_cache_key as cache_tests

load, SCRIPT = cache_tests.load, cache_tests.SCRIPT

IMAGE = 'immortalwrt-airoha-an7581-gemtek_w1700k-ubi-squashfs-sysupgrade.itb'
CONFIG = '''CONFIG_TARGET_airoha=y
CONFIG_TARGET_airoha_an7581=y
CONFIG_TARGET_airoha_an7581_DEVICE_gemtek_w1700k-ubi=y
CONFIG_TARGET_BOARD="airoha"
CONFIG_TARGET_SUBTARGET="an7581"
'''


class ReleaseTests(unittest.TestCase):
    def fixture(self, base):
        (base / 'scripts').symlink_to(ROOT / 'scripts')
        output = base / 'openwrt_bin/targets/airoha/an7581'
        output.mkdir(parents=True)
        (base / '.config').write_text(CONFIG)
        (output / IMAGE).write_bytes(b'fixture-not-firmware')
        data = {'target': 'airoha/an7581', 'version_code': 'r123-abcdef', 'profiles': {
            'gemtek_w1700k-ubi': {'supported_devices': ['gemtek,w1700k-ubi'],
                'titles': [{'vendor': 'Gemtek', 'model': 'W1700K', 'variant': 'UBI'}],
                'images': [{'name': IMAGE, 'type': 'sysupgrade', 'filesystem': 'squashfs', 'size': 20}]}}}
        (output / 'profiles.json').write_text(json.dumps(data))
        return output, data

    def stage(self, base, target='ubi2'):
        block = 'sudo() { "$@"; }; docker_exec() { shift; "$@"; };\n' + render(step('Stage firmware')['run'], {'matrix.target': target})
        return subprocess.run(['bash', '-eo', 'pipefail', '-c', block], cwd=base,
                              env=dict(os.environ, DK_OPENWRT=str(base)), text=True, capture_output=True)

    def test_stage_contract(self):
        for case in ('valid', 'oc', 'wrong-config', 'two-devices', 'missing-config', 'missing-target',
                     'wrong-json', 'two-profiles', 'wrong-supported', 'wrong-title', 'wrong-name',
                     'two-images', 'empty', 'missing-image', 'missing-json', 'bad-json', 'size', 'metadata-duplicate',
                     'metadata-name', 'filesystem', 'revision', 'other-target'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                out, data = self.fixture(base)
                profile = data['profiles']['gemtek_w1700k-ubi']
                config = base / '.config'
                image = out / IMAGE
                if case == 'wrong-config': config.write_text(CONFIG.replace('airoha', 'mediatek'))
                if case == 'two-devices': config.write_text(CONFIG + 'CONFIG_TARGET_airoha_an7581_DEVICE_other=y\n')
                if case == 'missing-config': config.unlink()
                if case == 'missing-target': config.write_text(CONFIG.replace('CONFIG_TARGET_airoha=y\n', ''))
                if case == 'wrong-json': data['target'] = 'mediatek/filogic'
                if case == 'two-profiles': data['profiles']['other'] = profile
                if case == 'wrong-supported': profile['supported_devices'] = ['other,board']
                if case == 'wrong-title': profile['titles'][0]['model'] = 'other'
                if case == 'wrong-name': image.rename(out / 'other-sysupgrade.itb')
                if case == 'two-images': (out / 'other-sysupgrade.itb').write_bytes(b'x')
                if case == 'empty': image.write_bytes(b'')
                if case == 'missing-image': image.unlink()
                if case == 'size': profile['images'][0]['size'] = 1
                if case == 'metadata-duplicate': profile['images'] *= 2
                if case == 'metadata-name': profile['images'][0]['name'] = 'other-sysupgrade.itb'
                if case == 'filesystem': profile['images'][0]['filesystem'] = 'ext4'
                if case == 'revision': data['version_code'] = None
                if case == 'other-target':
                    other = base / 'openwrt_bin/targets/mediatek/filogic'
                    other.mkdir(parents=True)
                    (other / IMAGE).write_bytes(b'x')
                (out / 'profiles.json').write_text(json.dumps(data))
                if case == 'missing-json': (out / 'profiles.json').unlink()
                if case == 'bad-json': (out / 'profiles.json').write_text('{')
                result = self.stage(base, 'ubi2-oc' if case == 'oc' else 'ubi2')
                if case in ('valid', 'oc'):
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((base / 'final.config').read_text(), CONFIG)
                    self.assertEqual((base / 'firmware' / IMAGE).read_bytes(), b'fixture-not-firmware')
                else:
                    self.assertNotEqual(result.returncode, 0, case)
                    self.assertFalse((base / 'firmware').exists())

    def test_publish_freshness_and_matrix_isolation(self):
        for target in ('ubi2', 'ubi2-oc'):
            for case in ('fresh', 'stale', 'error', 'empty', 'malformed', 'advance', 'recheck-error', 'create-error'):
                with self.subTest(target=target, case=case), tempfile.TemporaryDirectory() as tmp:
                    base = Path(tmp)
                    self.fixture(base)
                    result = self.stage(base, target)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    gh = base / 'gh'
                    gh.write_text('''#!/usr/bin/env python3
import os,json,sys
from pathlib import Path
args=sys.argv[1:]; root=Path(os.environ['STUB_ROOT']); mode=os.environ['CASE']
with (root/'calls').open('a') as f: f.write(json.dumps(args)+'\\n')
if args[0]=='api':
    second=(root/'checked').exists(); (root/'checked').touch()
    if mode=='error' or (second and mode=='recheck-error'): sys.exit(1)
    if mode=='empty': sys.exit(0)
    if mode=='malformed': print('null'); sys.exit(0)
    print('b'*40 if mode=='stale' or (second and mode=='advance') else os.environ['GITHUB_SHA'])
elif args[:2]==['release','create']:
    if mode=='create-error': sys.exit(1)
elif args[:2]==['release','list']:
    print((root/'tags').read_text())
elif args[:2]!=['release','delete']: sys.exit(99)
''')
                    gh.chmod(0o755)
                    version = (base / 'firmware/version.txt').read_text().strip()
                    standard = ['W1700K-ImmortalWrt_old', 'W1700K-ImmortalWrt-r1-old', 'W1700K-ubi2_old']
                    oc = ['W1700K-ImmortalWrt-OC_old', 'W1700K-ImmortalWrt-OC-r1-old', 'W1700K-ubi2-oc_old']
                    (base / 'tags').write_text('\n'.join(standard + oc + [version, 'unrelated']))
                    env = dict(os.environ, PATH=tmp + ':' + os.environ['PATH'], STUB_ROOT=tmp, CASE=case,
                               GITHUB_SHA='a'*40, GITHUB_REPOSITORY='fixture/repo')
                    result = subprocess.run(['bash', '-eo', 'pipefail', '-c', render(step('Create release')['run'], {'matrix.target': target})], cwd=base, env=env, text=True, capture_output=True)
                    calls = [json.loads(line) for line in (base / 'calls').read_text().splitlines()]
                    creates = [c for c in calls if c[:2] == ['release', 'create']]
                    deletes = [c[-1] for c in calls if c[:2] == ['release', 'delete']]
                    self.assertEqual(result.returncode == 0, case in ('fresh', 'stale', 'advance'), result.stderr)
                    self.assertEqual(bool(creates), case in ('fresh', 'advance', 'recheck-error', 'create-error'))
                    if creates: self.assertEqual(creates[0][creates[0].index('--target') + 1], 'a'*40)
                    self.assertEqual(set(deletes), set(standard if target == 'ubi2' else oc) if case == 'fresh' else set())
                    self.assertEqual(calls[0], ['api', 'repos/fixture/repo/git/ref/heads/main', '--jq', '.object.sha'])
                    if case == 'stale':
                        # A successful skipped publication leaves ordinary cache steps runnable.
                        block = 'docker_exec() { printf "%s\\n" "$*"; }; sudo() { :; };\n' + render(step('Pack caches')['run'], {'matrix.target': target, 'steps.tc.outputs.cache-hit': 'true'})
                        packed = subprocess.run(['bash', '-e', '-c', block], cwd=base, env=env, capture_output=True, text=True)
                        self.assertEqual(packed.returncode, 0)
                        self.assertIn('cache.py ccache', packed.stdout)


class LegacyRemovalTests(unittest.TestCase):
    setUp = cache_tests.KeyTests.setUp
    put = cache_tests.KeyTests.put
    key = cache_tests.KeyTests.key
    def test_rejected_admit(self):
        self.assertFalse(hasattr(self.cache, 'admit'))
        result = subprocess.run(['python3', str(SCRIPT), 'admit', str(self.root), str(Path(self.tmp.name)/'archive'), 'old'], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unknown cache mode', result.stderr)
        self.assertFalse((Path(self.tmp.name)/'archive').exists())
