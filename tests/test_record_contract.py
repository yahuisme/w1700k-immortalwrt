"""Shared record/publication contract; no network, Docker or compilation."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class RecordContract(unittest.TestCase):
    def fixture(self, base):
        profile = json.loads((ROOT / 'user/default/build.json').read_text())
        for path in (base, base / 'feeds/packages'):
            path.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'init', '-q', str(path)], check=True)
            subprocess.run(['git', '-C', str(path), '-c', 'user.name=Fixture', '-c',
                            'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture', '--allow-empty'], check=True)
            subprocess.run(['git', '-C', str(path), 'remote', 'add', 'origin', 'https://example.invalid/local'], check=True)
        (base / '.config').write_text('CONFIG_FIXTURE=y\n')
        (base / '.custom-revisions.tsv').write_text(''.join(
            f'{name}\thttps://example.invalid/{name}\t' + 'a' * 40 + '\n'
            for name in ('yahuisme/packages', 'luci-theme-aurora', 'luci-app-aurora-config')))
        target = base / 'bin/targets' / profile['target']
        target.mkdir(parents=True)
        (target / 'fixture.manifest').write_text('fixture - 1\n')
        (target / 'profiles.json').write_text('{}\n')
        paths = [target / name for name in profile['images']]
        for path in paths:
            path.write_bytes(b'fixture image')
        return profile, paths

    def run_record(self, base):
        return subprocess.run(['python3', str(ROOT / 'scripts/build_record.py'), str(base),
                               str(base / 'record')], capture_output=True, text=True)

    def test_versioned_record_and_legacy_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            profile, paths = self.fixture(base)
            (base / 'record').mkdir()
            environment = dict(repository='fixture/recipe', workflow_sha='b' * 40, run_id='1', run_attempt='2',
                               runner_os='Linux', runner_arch='ARM64', image_id='sha256:' + 'c' * 64,
                               builder_fingerprint='d' * 64)
            (base / 'record/environment.txt').write_text(''.join(f'{k}={v}\n' for k, v in environment.items()))
            result = self.run_record(base)
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads((base / 'record/build.json').read_text())
            revisions = json.loads((base / 'record/revisions.json').read_text())
            self.assertEqual(record['version'], 1)
            self.assertEqual(record['recipe']['workflow_sha'], 'b' * 40)
            self.assertEqual(record['builder']['image_id'], environment['image_id'])
            self.assertEqual(record['source'], revisions[0])
            self.assertEqual(record['feeds'] + record['custom_sources'], revisions[1:])
            self.assertEqual(record['target'], profile['target'])
            self.assertEqual(record['config']['digest'], 'sha256:' + hashlib.sha256((base / '.config').read_bytes()).hexdigest())
            self.assertEqual({e['name'] for e in record['images']}, {p.name for p in paths})
            self.assertEqual(json.loads((base / 'record/diagnostics.json').read_text()), dict(errors=[], warnings=[]))
            self.assertFalse((base / 'record/images.json').exists())
            self.assertFalse((base / 'record/source-revisions.txt').exists())

    def test_partial_failures_keep_config_revisions_and_diagnostics(self):
        for fault in ('empty', 'symlink', 'extra', 'wrong-name', 'missing', 'profiles', 'custom', 'git'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                profile, paths = self.fixture(base)
                image = paths[0]
                if fault == 'empty': image.write_bytes(b'')
                if fault == 'symlink':
                    image.rename(image.parent / 'payload')
                    image.symlink_to('payload')
                if fault == 'extra': (image.parent / ('extra-' + image.name)).write_bytes(b'extra')
                if fault == 'wrong-name': image.rename(image.parent / ('wrong-' + image.name))
                if fault == 'missing': image.unlink()
                if fault == 'profiles': (image.parent / 'profiles.json').unlink()
                if fault == 'custom': (base / '.custom-revisions.tsv').write_text('\n')
                if fault == 'git': (base / '.git').rename(base / 'hidden-git')
                result = self.run_record(base)
                self.assertNotEqual(result.returncode, 0)
                record = json.loads((base / 'record/build.json').read_text())
                self.assertIsNotNone(record['config'])
                self.assertTrue(json.loads((base / 'record/diagnostics.json').read_text())['errors'])
                self.assertTrue((base / 'record/revisions.json').exists())

    def test_explicit_profile_and_missing_profile_fail_closed(self):
        helper = module('build_profile')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, DK_PROFILE=tmp):
            with self.assertRaises(OSError): helper.load()
            data = json.loads((ROOT / 'user/default/build.json').read_text())
            (Path(tmp) / 'build.json').write_text(json.dumps(data))
            self.assertEqual(helper.load(), data)

    def test_readback_contract(self):
        helper = module('verify_release')
        for fault in ('ok', 'missing', 'extra', 'duplicate', 'name', 'size', 'state', 'digest',
                      'tag', 'draft', 'prerelease', 'download', 'download-wrong', 'download-failure'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                profile, paths = self.fixture(base)
                digest = 'sha256:' + hashlib.sha256(b'fixture image').hexdigest()
                assets = [dict(id=i, name=p.name, size=p.stat().st_size, state='uploaded', digest=digest)
                          for i, p in enumerate(paths, 1)]
                release = dict(tag_name='tag/a', draft=False, prerelease=False, assets=assets)
                if fault == 'missing': assets.pop()
                if fault == 'extra': assets.append(dict(assets[0], name='extra'))
                if fault == 'duplicate': assets.append(dict(assets[0]))
                if fault == 'name': assets[0]['name'] = 'wrong'
                if fault == 'size': assets[0]['size'] += 1
                if fault == 'state': assets[0]['state'] = 'new'
                if fault == 'digest': assets[0]['digest'] = 'sha256:' + '0' * 64
                if fault == 'tag': release['tag_name'] = 'wrong'
                if fault in ('draft', 'prerelease'): release[fault] = True
                if fault.startswith('download'):
                    for asset in assets: asset.pop('digest')
                class Download:
                    stdout = io.BytesIO(b'wrong' if fault == 'download-wrong' else b'fixture image')
                    def __enter__(self):
                        self.stdout = io.BytesIO(b'wrong' if fault == 'download-wrong' else b'fixture image')
                        return self
                    def __exit__(self, *args): self.stdout.close()
                    def wait(self): return 17 if fault == 'download-failure' else 0
                with patch.dict(os.environ, GITHUB_REPOSITORY='fixture/repo'), \
                     patch.object(helper.subprocess, 'check_output', return_value=json.dumps(release).encode()) as api, \
                     patch.object(helper.subprocess, 'Popen', side_effect=lambda *a, **k: Download()) as download, \
                     contextlib.redirect_stdout(io.StringIO()):
                    if fault in ('ok', 'download'):
                        helper.verify('tag/a', paths)
                        self.assertIn('/tags/tag%2Fa', api.call_args[0][0][-1])
                        self.assertEqual(download.call_count, len(paths) if fault == 'download' else 0)
                    else:
                        with self.assertRaises(ValueError): helper.verify('tag/a', paths)

    def test_local_release_set_rejected_before_api(self):
        helper = module('verify_release')
        for fault in ('empty-list', 'duplicate', 'missing', 'name', 'empty', 'symlink'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                _, paths = self.fixture(base)
                if fault == 'empty-list': paths = []
                if fault == 'duplicate': paths.append(paths[0])
                if fault == 'missing': paths[0].unlink()
                if fault == 'name':
                    paths[0].rename(paths[0].parent / 'wrong.itb')
                    paths[0] = paths[0].parent / 'wrong.itb'
                if fault == 'empty': paths[0].write_bytes(b'')
                if fault == 'symlink':
                    paths[0].rename(paths[0].parent / 'payload')
                    paths[0].symlink_to('payload')
                with patch.object(helper.subprocess, 'check_output') as api:
                    with self.assertRaises(ValueError): helper.verify('tag', paths)
                    api.assert_not_called()
