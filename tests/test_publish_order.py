"""Replay real YAML order/conditions and shell; mock only external services/builds."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_cache_workflow import ROOT, STEPS, step, render
from test_cache_helper import GH, entry
import test_release_safety as release


class PublishOrderTests(unittest.TestCase):
    def test_stage_status_gate_after_complete_cache_tail(self):
        publish = step('Publish firmware and prune releases')
        self.assertEqual(step('Validate and stage firmware').get('id'), 'stage')
        self.assertEqual(publish.get('if'), "${{ !cancelled() && steps.stage.outcome == 'success' }}")
        self.assertEqual(publish['env'], {'GH_TOKEN': '${{ secrets.RELEASE_TOKEN }}'})
        self.assertEqual(STEPS[-1], publish)
        self.assertLess(STEPS.index(step('Prune old download caches')), STEPS.index(publish))
        for item in STEPS[STEPS.index(step('Package build caches')):STEPS.index(publish)]:
            self.assertNotRegex(item.get('if', ''), r'\b(always|failure|cancelled)\(')
            self.assertFalse(item.get('continue-on-error', False))

    def replay(self, fault):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            release.ReleaseTests().fixture(base)
            if fault == 'validation':
                (base / '.config').write_text('CONFIG_TARGET_wrong=y\n')
            cc = base / 'staging_dir/host/bin/ccache'
            cc.parent.mkdir(parents=True)
            cc.write_text('#!/bin/sh\nexit 0\n')
            cc.chmod(0o755)
            for directory in ('ccarchive', 'tcarchive', 'dlarchive', 'dlcache'):
                (base / directory).mkdir()
            state = base / 'state.json'
            old = [entry(1, 'cc-v3-ubi2.old'), entry(2, 'tc-v3-ubi2-old'), entry(3, 'dl-v3.old')]
            state.write_text(json.dumps(dict(entries=old, calls=[], reads=0,
                                             fail_reads=[2] if fault == 'readback' else [])))
            gh = GH.replace("if a == ['api', '--paginate'", """if a[:2] == ['api', 'repos/fixture/repo/git/ref/heads/main']:
    p.write_text(json.dumps(s)); print(os.environ['GITHUB_SHA']); sys.exit(0)
elif a[:2] == ['release', 'create']:
    p.write_text(json.dumps(s)); sys.exit(19 if os.environ['FAULT']=='publish' else 0)
elif a[:2] == ['release', 'list']:
    p.write_text(json.dumps(s)); print('W1700K-ImmortalWrt_old'); sys.exit(0)
elif a[:2] == ['release', 'delete']:
    p.write_text(json.dumps(s)); sys.exit(0)
elif a == ['api', '--paginate'""")
            (base / 'gh').write_text(gh)
            (base / 'gh').chmod(0o755)
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ['PATH'],
                       MOCK_STATE=str(state), GITHUB_REF='refs/heads/main',
                       GITHUB_SHA='a'*40, GITHUB_REPOSITORY='fixture/repo',
                       GITHUB_OUTPUT=str(base / 'output'), RUNNER_TEMP=tmp,
                       DK_OPENWRT=tmp, FAULT=fault)
            # Real nested compile shell and stage; compiler, Docker and archive
            # compressor are external boundaries. No firmware build/network occurs.
            prefix = '''
make() { [ "$FAULT" != compile ]; }
docker_exec() {
    shift
    if [ "$1" = python3 ] && [ "$2" = /cache-scripts/cache.py ]; then
        [ "$FAULT" != package ] || return 17
        mkdir -p "${5#/}"
        truncate -s 100 "${5#/}/$3.tar.gz"
    else
        "$@"
    fi
}
sudo() { "$@"; }
export -f make docker_exec sudo
'''
            subprocess.run(['python3', str(ROOT/'scripts/dlcache.py'), 'snapshot',
                            str(base/'dlcache'), str(base/'dlcache-before.json')], check=True,
                           capture_output=True)
            (base/'dlcache/new-download').write_bytes(b'fixture download')
            values = {'steps.tc.outputs.cache-hit': 'false',
                      'steps.inputs.outputs.key': 'tc-v3-ubi2-new',
                      'steps.gh.outputs.cache-primary-key': 'cc-v3-ubi2.new',
                      'steps.dl.outputs.cache-primary-key': 'dl-v3.new',
                      'steps.dl.outputs.cache-matched-key': '',
                      'steps.stage.outcome': 'skipped'}
            successful, cancelled = True, False
            outcomes, executed, logs = {}, [], []
            def condition(expr):
                expression = expr.removeprefix('${{').removesuffix('}}').strip()
                status = re.search(r'\b(success|failure|cancelled|always)\(', expression)
                if not status and (not successful or cancelled):
                    return False  # Actions implicit success(), not just expression truth.
                for token, value in [('!cancelled()', not cancelled), ('cancelled()', cancelled),
                                     ('success()', successful), ('failure()', not successful), ('always()', True)]:
                    expression = expression.replace(token, repr(value))
                expression = re.sub(r"hashFiles\('([^']+)'\)",
                                    lambda m: repr('present' if (base/m[1]).exists() else ''), expression)
                expression = re.sub(r'steps\.[\w.-]+', lambda m: repr(values.get(m[0], '')), expression)
                # Only trusted repository comparisons and repr-quoted local
                # fixture values are evaluated, never external/event input.
                return eval(expression.replace('&&', ' and '), {'__builtins__': {}})
            for item in STEPS[STEPS.index(step('Compile firmware')):]:
                name = item['name']
                if fault == 'cancel' and name == 'Package build caches':
                    cancelled = True
                if not condition(item.get('if', 'True')):
                    outcomes[name] = 'skipped'
                    continue
                executed.append(name)
                if 'run' in item:
                    result = subprocess.run(['bash', '-eo', 'pipefail', '-c', prefix + render(item['run'], values)],
                                            cwd=base, env=env, text=True, capture_output=True)
                    rc = result.returncode
                    logs.append(name + '\n' + result.stdout + result.stderr)
                else:
                    self.assertEqual(item['uses'], 'actions/cache/save@main')
                    rc = 23 if fault == 'save' else 0
                    if not rc:
                        inventory = json.loads(state.read_text())
                        inventory['entries'].append(entry(100+len(executed), render(item['with']['key'], values)))
                        state.write_text(json.dumps(inventory))
                outcome = 'success' if rc == 0 else 'failure'
                outcomes[name] = outcome
                if item.get('id'):
                    values[f"steps.{item['id']}.outcome"] = outcome
                    output = base/'output'
                    if output.exists():
                        for line in output.read_text().splitlines():
                            k, v = line.split('=', 1)
                            values[f"steps.{item['id']}.outputs.{k}"] = v
                        output.unlink()
                successful = successful and rc == 0
            return outcomes, executed, json.loads(state.read_text()), '\n'.join(logs)

    def test_full_compile_stage_cache_publish_failure_matrix(self):
        for fault in ('none', 'compile', 'validation', 'cancel', 'package', 'save', 'readback', 'publish'):
            with self.subTest(fault=fault):
                outcomes, executed, inventory, log = self.replay(fault)
                published = fault not in ('compile', 'validation', 'cancel')
                creates = [call for call in inventory['calls'] if call[:2] == ['release', 'create']]
                self.assertEqual(bool(creates), published, log)
                self.assertEqual(outcomes['Publish firmware and prune releases'],
                                 'failure' if fault == 'publish' else 'success' if published else 'skipped', log)
                if fault in ('none', 'publish'):
                    self.assertEqual({item['key'] for item in inventory['entries']},
                                     {'cc-v3-ubi2.new', 'tc-v3-ubi2-new', 'dl-v3.new'}, log)
                    self.assertLess(executed.index('Prune old download caches'),
                                    executed.index('Publish firmware and prune releases'))
                else:
                    self.assertTrue({1, 2, 3} <= {item['id'] for item in inventory['entries']}, log)
                if fault in ('save', 'readback'):
                    self.assertEqual(outcomes['Check toolchain cache budget'], 'skipped', log)
