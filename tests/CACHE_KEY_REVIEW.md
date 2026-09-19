# Exact host-artifact cache

## Contract

The key hashes the complete final `.config`, source contents and modes under
`INPUTS`, builder fingerprint, host architecture, build path and fingerprint policy.
`tc-inputs-v7` replaces image-ID compatibility; the workflow still inspects and
runs the exact local `IMAGE_ID`, but never hashes OCI creation timestamps.

`scripts/builder_fingerprint.py` runs inside that container before source prep.
Policy `builder-v1` hashes the names and per-file SHA256 of actual recipe inputs
(currently **only Dockerfile**, because it has no COPY/ADD), the SHA256 of its own
implementation, `platform.machine()`, and the complete sorted `dpkg-query`
package/architecture/version inventory. Empty or failing inventory, a missing
Dockerfile or a symlinked Dockerfile is rejected. The pinned official Debian base
and official Go archive checksum are covered by Dockerfile bytes. Adding COPY/ADD
requires extending the explicit input list and reviewing this contract.

README, smoke script and .dockerignore edits do not invalidate the toolchain key:
none currently contributes bytes to the built environment. File mtimes, inventory
order, image IDs and container IDs also do not invalidate it. Rolling apt package
updates do. This controlled-recipe contract is not arbitrary-image equivalence
or a claim of bit-reproducible apt/image contents. Do not introduce mutable
non-dpkg downloads, build-arg overrides or ad-hoc container mutations without
verified identities in this contract. Implementation changes invalidate identity.

Only toolchain restore is exact (no prefix fallback). Existing compiler/download
cache prefixes, sizes, repository admission budget and scheduling are unchanged.
There is no CONFIG projection, audited-source lock or historical commit dependency.
This policy change deliberately starts a new exact-key generation; no old-key
fallback is allowed. Package/version settings and literal DEFAULT_PACKAGES changes
remain invalidators. External mutable compiler/kernel/source trees are rejected.

Only the three explicit generic/Airoha runtime `base-files` overlays and ignored
`scripts/config` generated outputs are excluded. Kernel files/patches and target
recipes remain inputs. Input mtimes are normalized to `EPOCH`; completion stamps
are never touched. PAX archives preserve nanoseconds and restore matching
`build_dir/host`, `build_dir/toolchain-*`, `staging_dir/host` and
`staging_dir/toolchain-*` together after clearing old build/staging trees.

## Reproduce

```sh
python3 -m unittest discover -s tests -p 'test_cache_key.py' -v
python3 -m unittest discover -s tests -p 'test_builder_image.py' -v
# No compilation: default process, mounts, Go/tool availability and cache primitives
# Run docker/smoke.sh in an empty-source builder, not a prepared buildroot.
# Disposable, configured Airoha/an7581 source with native host build prerequisites:
python3 tests/check_cache_upstream.py "$PREPARED_BUILDROOT"
```

The opt-in check reads dependency rules from the supplied current source, checks
full-config invalidation, expands real kernel-header stamp variables, compiles
`tools/flock`, then compresses/deletes/restores artifacts and runs warm make.
It requires unchanged nanosecond `.built` and no flock compiler command after
restore; a source-content mutation must miss and compile on the cold path.
It modifies the supplied disposable tree. Empty toolchain layout fixtures are
**not GCC validation**. These checks do not establish full firmware build speed.

## Compression choice

Packing uses `pigz -1` when already installed, otherwise `gzip -1`; extraction
continues to use gzip-compatible tar. No installation is performed by this helper.
The historical `ghcr.io/w1700k/fastbuild_base:base-builder` test image
(`8563dec89b4c`, aarch64) had gzip but **no pigz**. It is no longer used by
the workflow; the measurements below describe that historical environment,
not the current official Debian builder.

A PAX sample of real source plus native flock build/staging files gave these
three-run median compression-only measurements (not a production-size cache):

| Environment | Compressor | Seconds | Bytes |
| --- | --- | ---: | ---: |
| builder, root | gzip default | 0.1234 | 1096478 |
| builder, root | gzip -1 | 0.0613 | 1279603 |
| host, existing executable | pigz -1 | 0.0164 | 1274209 |

Level 1 trades a larger archive for lower local compression time. Existing
compressed-size caps still apply; this sample does not prove full-cache capacity
or CI wall-time improvement. Pigz's host result does not imply builder availability.
Reproduce on the same sample, checking executables in the actual builder first:

```sh
tar --format=posix -cf sample.tar -C "$PREPARED_BUILDROOT" \
  tools toolchain include scripts build_dir/host staging_dir/host
/usr/bin/time gzip -c sample.tar > default.gz
/usr/bin/time gzip -1 -c sample.tar > fast.gz
# Only where command -v pigz succeeds:
/usr/bin/time pigz -1 -c sample.tar > parallel.gz
wc -c default.gz fast.gz parallel.gz
```
