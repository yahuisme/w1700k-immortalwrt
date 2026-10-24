"""Hash-only projection of final defconfig bytes; never rewrite .config."""
from pathlib import Path
import re


def fingerprint_bytes(raw):
    """Project only unambiguous generated LF config; unknown formats stay raw.

    GNU make ignores unset comments, but explicit =n is a defined variable.
    Reject duplicate symbols across BOTH assignments and unset comments before
    dropping anything: raw consumers can observe conflicting input differently.
    """
    if not raw or not raw.endswith(b'\n') or b'\r' in raw:
        return raw
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw
    if any(ord(char) == 127 or ord(char) < 32 and char not in '\n\t' for char in text):
        return raw
    seen, kept = set(), []
    boost_defined = False
    # Audited package-only Kconfig selectors, removed by the Boost recipe.
    # Any explicit Boost package assignment keeps these records in the lock.
    boost_unset = {f'# CONFIG_boost-{name}-exclude is not set\n'
                   for name in ('context', 'coroutine', 'fiber')}
    for line in text.splitlines(keepends=True):
        # Avoid make comment continuations and unfamiliar line separators.
        if not line.endswith('\n') or line.endswith('\\\n'):
            return raw
        unset = re.fullmatch(r'# (CONFIG_[A-Za-z0-9_+.-]+) is not set\n', line)
        assignment = re.fullmatch(
            r'(CONFIG_[A-Za-z0-9_+.-]+)=(y|m|n|-?[0-9]+|0x[0-9a-fA-F]+|"(?:[^"\\\x00-\x1f]|\\["\\])*")\n', line)
        if assignment and ('$' in line or '`' in line):
            return raw
        if unset is not None or assignment is not None:
            match = unset if unset is not None else assignment
            assert match is not None
            symbol = match[1]
            if symbol == 'CONFIG_PACKAGE_' or symbol in seen:
                return raw
            seen.add(symbol)
            if assignment and (symbol == 'CONFIG_PACKAGE_boost' or symbol.startswith('CONFIG_PACKAGE_boost-')):
                boost_defined = True
        elif line != '\n' and (not line.startswith('#') or line[1:].lstrip().startswith('CONFIG_')):
            return raw
        if not unset or not unset[1].startswith('CONFIG_PACKAGE_') or unset[1] == 'CONFIG_PACKAGE_':
            kept.append(line)
    return ''.join(line for line in kept if boost_defined or line not in boost_unset).encode('utf-8')


def policy_bytes():
    """Lock the entire shared algorithm, not just the caller's import statement."""
    return Path(__file__).read_bytes()
