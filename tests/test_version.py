"""Run workflow versioning through real upstream getver/version.mk/templates.

Usage: IMMORTALWRT_SOURCE=/path/to/official/git/checkout python3 tests/test_version.py
The checkout is read-only; all rendering and version caches live in temporary dirs.
No firmware compilation or device execution is implied by these tests.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

REPO = Path(__file__).resolve().parents[1]
SOURCE = os.environ.get("IMMORTALWRT_SOURCE")


def run(args, cwd, **kwargs):
    return subprocess.check_output(args, cwd=cwd, text=True, **kwargs)


class VersionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE:
            raise RuntimeError("Set IMMORTALWRT_SOURCE to the official ImmortalWrt git checkout")
        cls.source = Path(SOURCE).resolve()
        cls.sha = run(["git", "rev-parse", "HEAD"], cls.source).strip()
        cls.files = {}
        for name in ["scripts/getver.sh", "include/version.mk", "include/toplevel.mk",
                     "package/base-files/Makefile", "scripts/json_add_image_info.py",
                     "include/image.mk", "rules.mk"]:
            cls.files[name] = run(["git", "show", f"HEAD:{name}"], cls.source)
        # Get the actual install input list, not a second hand-maintained template list.
        install = re.search(r"\$\(VERSION_SED_SCRIPT\) \\\n(.*?)(?=\n\s*\n)",
                            cls.files["package/base-files/Makefile"], re.S)
        assert install is not None, "Upstream base-files template install changed"
        cls.templates = re.findall(r"\$\(1\)/(\S+)", install.group(1))
        for name in cls.templates:
            cls.files[name] = run(["git", "show", "HEAD:package/base-files/files/" + name], cls.source)
        workflow = (REPO / ".github/workflows/W1700K.yaml").read_text()
        cls.fragment = textwrap.dedent(workflow.split("          make defconfig\n", 1)[1]
                                      .split("          make download", 1)[0])
        cls.tag = textwrap.dedent(workflow.split('        PREFIX="W1700K-ImmortalWrt_"', 1)[1]
                                 .split('        RELEASE_NOTES=', 1)[0])
        cls.tag = 'PREFIX="W1700K-ImmortalWrt_"\n' + cls.tag

    def prepare(self, root):
        for name, content in self.files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        (root / "scripts/getver.sh").chmod(0o755)
        # A real git worktree view without copying history or mutating the source.
        gitdir = run(["git", "rev-parse", "--absolute-git-dir"], self.source).strip()
        (root / ".git").write_text(f"gitdir: {gitdir}\n")
        (root / ".config").write_text('CONFIG_VERSION_CODE=""\nCONFIG_VERSION_DIST="ImmortalWrt"\n')

    def render(self, root):
        # Execute upstream's top-level REVISION assignment and full version.mk.
        revision = next(line for line in self.files["include/toplevel.mk"].splitlines()
                        if line.strip().startswith("REVISION:="))
        rules = self.files["rules.mk"]
        qstrip = next(line for line in rules.splitlines() if line.startswith("qstrip="))
        makefile = f"""TOPDIR:=$(CURDIR)
include .config
empty:=
space:=$(empty) $(empty)
comma:=,
{qstrip}
tolower=$(shell printf '%s' '$(1)' | tr A-Z a-z)
SED:=sed -i -e
BOARD:=airoha
SUBTARGET:=an7581
ARCH_PACKAGES:=aarch64_cortex-a53
SOURCE_DATE_EPOCH:=1
{revision}
include include/version.mk
all:
\t$(VERSION_SED_SCRIPT) {' '.join(self.templates)}
\t@printf '%s\\n' '$(REVISION)' '$(VERSION_CODE)' > values
\t@VERSION_CODE='$(VERSION_CODE)' VERSION_NUMBER='$(VERSION_NUMBER)' SOURCE_DATE_EPOCH=1 FILE_DIR=. FILE_NAME=sample.itb DEVICE_ID=gemtek_w1700k DEVICE_PACKAGES='' SUPPORTED_DEVICES=gemtek,w1700k python3 scripts/json_add_image_info.py firmware/profiles.json
"""
        (root / "Makefile").write_text(makefile)
        (root / "sample.itb").write_bytes(b"test image payload, not a firmware")
        (root / "firmware").mkdir(exist_ok=True)
        run(["make", "--no-print-directory"], root)
        return {name: (root / name).read_bytes() for name in self.templates}

    def check_variant(self, variant, cached=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare(root)
            env = os.environ.copy()
            env.pop("TOPDIR", None)
            original = run(["./scripts/getver.sh"], root, env=env).strip()
            match = re.fullmatch(r"r([0-9]+)(-[0-9a-f]+)", original)
            assert match is not None, original
            self.assertTrue(self.sha.startswith(match[2][1:]), (self.sha, original))
            expected = f"r{int(match[1]) + (variant == 'ubi2-oc')}{match[2]}"
            if cached:
                (root / "version").write_text("r1-deadbeef\n")
            fragment = self.fragment.replace("${{ matrix.target }}", variant)
            run(["bash", "-e", "-c", fragment], root, env=env)
            rendered = self.render(root)
            self.assertEqual((root / "values").read_text().splitlines(), [expected, expected])
            self.assertEqual(run(["./scripts/getver.sh"], root, env=env).strip(), expected)
            if variant == "ubi2-oc":
                self.assertEqual((root / "version").read_text(), expected + "\n")
                # A repeat prepare must derive from git, not increment yesterday's cache.
                run(["bash", "-e", "-c", fragment], root, env=env)
                self.assertEqual(run(["./scripts/getver.sh"], root, env=env).strip(), expected)
            release = rendered["etc/openwrt_release"].decode()
            os_release = rendered["usr/lib/os-release"].decode()
            self.assertIn(f"DISTRIB_REVISION='{expected}'", release)
            self.assertIn(f"DISTRIB_DESCRIPTION='ImmortalWrt {variant} {expected}'", release)
            self.assertIn(f'BUILD_ID="{expected}"', os_release)
            self.assertIn(f'OPENWRT_RELEASE="ImmortalWrt {variant} {expected}"', os_release)
            self.assertEqual(rendered["etc/openwrt_version"], (expected + "\n").encode())
            self.assertIn(expected.encode(), rendered["etc/banner"])
            profiles = json.loads((root / "firmware/profiles.json").read_text())
            self.assertEqual(profiles["version_code"], expected)
            self.assertEqual(profiles["version_number"], variant)
            run(["bash", "-e", "-c", self.tag.replace("${{ matrix.target }}", variant)], root, env=env)
            prefix = "W1700K-ImmortalWrt" + ("-OC" if variant == "ubi2-oc" else "")
            self.assertTrue((root / "firmware/version.txt").read_text().startswith(
                prefix + "-" + expected.split("-")[0] + "-"))
            self.assertEqual(run(["git", "rev-parse", "HEAD"], root).strip(), self.sha)
            if variant == "ubi2":
                self.assertFalse((root / "version").exists())
                # Baseline is upstream rendering with the original workflow's standard config.
                self.prepare(root)
                with (root / ".config").open("a") as config:
                    config.write("CONFIG_VERSION_NUMBER=ubi2\n")
                self.assertEqual(self.render(root), rendered)

    def test_oc_all_version_consumers(self):
        self.check_variant("ubi2-oc")

    def test_oc_ignores_stale_version_cache(self):
        self.check_variant("ubi2-oc", cached=True)

    def test_standard_bytes_unchanged(self):
        self.check_variant("ubi2")

    def test_oc_rejects_unknown_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare(root)
            (root / ".git").unlink()
            result = subprocess.run(
                ["bash", "-e", "-c", self.fragment.replace("${{ matrix.target }}", "ubi2-oc")],
                cwd=root, text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unexpected revision: unknown", result.stdout)
            self.assertFalse((root / "version").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
