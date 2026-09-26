"""Singleton profile wiring and complete preparation block, local I/O only."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import yaml
from test_cache_workflow import ROOT, WORKFLOW, step


class SingleProfileTests(unittest.TestCase):
    def test_direct_profile_and_complete_preparation(self):
        workflow = yaml.safe_load(WORKFLOW.read_text())
        self.assertEqual(workflow['jobs']['build']['env']['DK_PROFILE'], '/bld/user/default')
        self.assertNotIn('user/current', WORKFLOW.read_text())
        self.assertNotIn('rsync', step('Start build container')['run'])
        profile = ROOT/'user/default'
        original = {str(p.relative_to(profile)): p.read_bytes() for p in profile.rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            copied = base/'user/default'
            shutil.copytree(profile, copied)
            legacy = base/'legacy'
            subprocess.run(['rsync', '-aI', '--mkpath', str(profile)+'/', str(legacy)+'/'], check=True)
            with (legacy/'config.diff').open('a') as stream:
                stream.write('CONFIG_CCACHE_DIR="/ghcache"\n')
            expected = (legacy/'config.diff').read_bytes()
            for name, data in original.items():
                if name != 'config.diff':
                    self.assertEqual((legacy/name).read_bytes(), data)
            # Native shell executes the complete YAML preparation. Source Git,
            # feeds/download/build, customization are explicit external fixture
            # boundaries; actual complete custom + defconfig are separately tested
            # against the source-backed prepared tree, never compiled locally.
            (copied/'custom.sh').write_text('''#!/bin/bash
set -e
cmp .config "$EXPECTED"
cmp feeds.conf "$DK_PROFILE/feeds.conf"
diff -qr files "$DK_PROFILE/files"
test "$DK_PROFILE" = "$EXPECTED_PROFILE"
printf '%s\\n' custom >> "$LOG"
''')
            build = base/'build'
            (build/'scripts').mkdir(parents=True)
            (build/'scripts/feeds').write_text('#!/bin/bash\nprintf "feeds %s\\n" "$*" >> "$LOG"\n')
            (build/'scripts/feeds').chmod(0o755)
            for name in ('feeds/packages/.git', 'package/luci-theme-aurora/.git', 'package/luci-app-aurora-config/.git'):
                (build/name).mkdir(parents=True)
            block = step('inputs')['run']
            stubs = '''
docker_exec() {
    shift
    if [ "$1" = python3 ]; then printf 'fixture-key\\n'; else "$@"; fi
}
git() { printf 'git %s\\n' "$*" >> "$LOG"; if [[ "$*" = *rev-parse* ]]; then printf '%040d\\n' 1; fi; }
mountpoint() { return 0; }
make() { printf 'make %s\\n' "$*" >> "$LOG"; }
export -f docker_exec git mountpoint make
'''
            env = dict(os.environ, DK_PROFILE=str(copied), DK_OPENWRT=str(build),
                       DK_BIN=str(base/'bin'), EXPECTED=str(legacy/'config.diff'),
                       EXPECTED_PROFILE=str(copied), LOG=str(base/'calls'),
                       GITHUB_OUTPUT=str(base/'output'), BUILDER_FINGERPRINT='fixture')
            result = subprocess.run(['bash', '-eo', 'pipefail', '-c', stubs+block],
                                    cwd=base, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertEqual((build/'.config').read_bytes(), expected)
            self.assertEqual((copied/'config.diff').read_bytes(), original['config.diff'])
            calls = (base/'calls').read_text()
            self.assertLess(calls.index('custom\n'), calls.index('make defconfig'))
            self.assertIn('make download -j8', calls)
            self.assertEqual((base/'output').read_text(), 'key=tc-v3-ubi2-fixture-key\n')
        self.assertEqual({str(p.relative_to(profile)): p.read_bytes() for p in profile.rglob('*') if p.is_file()}, original)
