# Exact host-artifact cache

## Contract

The key hashes the complete final `.config`, source contents and modes under
`INPUTS`, builder fingerprint, host architecture, build path and fingerprint policy.
`tc-inputs-v8` replaces image-ID compatibility; the workflow still inspects and
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

Toolchain restore remains exact (no prefix fallback); its key and archive format
are unchanged by diagnostics or the independent compiler-bootstrap tier. Existing
compiler/download namespaces and scheduling are retained. The toolchain policy
has no CONFIG projection or audited-source lock. Package/version settings and
literal DEFAULT_PACKAGES changes remain invalidators. External mutable compiler,
kernel and source trees are rejected. Bootstrap's narrower audited contract is
separate; it does not authorize restoring an incompatible cross-toolchain.

The three explicit generic/Airoha runtime `base-files` overlays and ignored
`scripts/config` generated outputs are excluded. Recognized direct generic
`backport/pending/hack/files/config/kernel-<version>` roots for versions not
declared by the Airoha platform/subtargets are also excluded when every version
expression is understood and a normal KERNEL_PATCHVER is present. Unknown
expressions/includes or missing normal versions retain the full generic tree;
shared/unrecognized roots and symlinks are not excluded by version. Selected
kernel files/patches and target recipes remain inputs. Input mtimes are normalized to `EPOCH`; completion stamps
are never touched. PAX archives preserve nanoseconds and restore matching
`build_dir/host`, `build_dir/toolchain-*`, `staging_dir/host` and
`staging_dir/toolchain-*` together after clearing old build/staging trees.

## Independent compiler bootstrap

`tb-v1-ubi2-` is an exact, optional companion to the existing toolchain cache.
It is queried only after an exact toolchain miss. A hit restores the paired
host build/staging snapshot and still runs `make tools/ccache/compile`; GNU make,
not a manually touched stamp, decides whether work is needed. A cold snapshot
is packed immediately after that target and **before world**, because later
package recipes can write to `staging_dir/host`. Never seed it from a completed
world tree or merge it with a mismatched cross-toolchain.

The bootstrap key keeps the entire final `.config`, builder identity, host
architecture and absolute build path. Independent reuse requires the audited
post-customization tools/scripts/framework input inventory. Unknown framework
content falls back conservatively to compatibility tied to the full toolchain
key; there is no all-package CONFIG projection or prefix restore. Kernel and
runtime changes can preserve bootstrap only while those audited consumers,
configuration and environment remain unchanged.

The bootstrap compressed cap is 1,000,000,000 bytes within the existing
10,000,000,000-byte repository budget. Admission counts all old/new generations
and wrapper margin. Confirm a nonempty current-ref upload before pruning its
own old prefix. Compiler → toolchain → bootstrap → download sequencing keeps
unconfirmed uploads from admitting another tier. Denied admission retains old
seeds; this is not a guarantee that every tier at its maximum can roll over.

Diagnostics emit one `cache-inputs sha256/16` line from the same serialized
records as the unchanged toolchain key, without a second source scan. Compile
logs separately time bootstrap and world, including their failure exit status.

Tests exercise actual YAML shell with build/API boundaries stubbed and native
PAX archive operations without compilation. Fixture scripts are not proof of
restored CMake/GCC execution or measured CI acceleration. Production archive
size, stamp reuse and net wall-time savings require a separately authorized
real build; do not promise a fixed duration.

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

## Download capacity regression

Download packing and admission both allow exactly **3,200,000,000 bytes**.
The 10,000,000,000-byte repository budget, 64 MiB minimum wrapper margin,
keys and save → confirmation → old-generation pruning remain unchanged.
`test_cache_helper.py` replays the saved paginated inventories in
`fixtures/download-cache-inventory.json`, measured 2.403/2.356 GB outputs,
sparse cap/cap+1 and old/new coexistence with the measured other tiers.
Every replacement is rejected when all tiers already occupy their maxima;
The per-download cap does not guarantee unlimited rollover headroom.
Compression alone is stubbed for size tests; these are not speed benchmarks.

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
