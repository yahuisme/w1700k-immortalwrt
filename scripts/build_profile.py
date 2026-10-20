#!/usr/bin/env python3
"""Load the checked-in build contract shared by CI helpers."""
import json
import os
from pathlib import Path
import re


def load(profile=None):
    # Runner helpers use the checked-out profile, even when DK_PROFILE names
    # a container-only mount. In /cache-scripts that checkout is absent, so
    # container helpers use the explicitly mounted DK_PROFILE instead.
    profile = Path(profile or os.environ.get('DK_PROFILE') or Path(__file__).resolve().parents[1] / 'user/default')
    if not (profile / 'build.json').is_file() and os.environ.get('DK_PROFILE'):
        profile = Path(os.environ['DK_PROFILE'])
    data = json.loads((profile / 'build.json').read_text())
    if data['system'] not in ('openwrt', 'immortalwrt') or data['device'] not in ('W1700K', 'MX4200'):
        raise ValueError('unsupported build system/device')
    if not re.fullmatch(r'[a-z0-9_]+/[a-z0-9_]+', data['target']):
        raise ValueError('invalid target')
    if not data['images'] or len(set(data['images'])) != len(data['images']):
        raise ValueError('missing or duplicate release images')
    for name in data['images']:
        if Path(name).name != name or not name.startswith(data['system'] + '-'):
            raise ValueError('invalid release image name')
    if set(data['cache_prefix']) != {'tc', 'cc', 'dl'} or any(not v for v in data['cache_prefix'].values()):
        raise ValueError('incomplete cache namespaces')
    return data
