#!/bin/bash

set -e

echo "=============================================="
echo "Running custom commands"

# -------------------------------------------------
# Fetch W1700K-specific packages from OpenW1700k
# -------------------------------------------------
# luci-app-wifi7 / luci-app-mlo / luci-app-airoha-npu /
# luci-app-airoha-flowsense / luci-app-w1700k-fancontrol
# are not available in ImmortalWrt feeds. Follow the OpenW1700k ubi2
# branch at build time (no version pinning).
FORK=/tmp/openw1700k
if ! git clone --depth=1 --filter=blob:none --sparse --branch ubi2 \
    https://github.com/OpenWRT-fanboy/OpenW1700k.git "$FORK"; then
    echo "ERROR: Failed to clone OpenW1700k fork!"
    exit 1
fi
git -C "$FORK" sparse-checkout set \
    package/luci-app-wifi7 package/luci-app-mlo package/luci-app-airoha-npu \
    package/luci-app-airoha-flowsense package/luci-app-w1700k-fancontrol
cp -r "$FORK/package/luci-app-wifi7" "$FORK/package/luci-app-mlo" \
      "$FORK/package/luci-app-airoha-npu" "$FORK/package/luci-app-airoha-flowsense" \
      "$FORK/package/luci-app-w1700k-fancontrol" package/


# -------------------------------------------------
# Sync W1700K platform patches from OpenW1700k ubi2 (dynamic, follows upstream)
# -------------------------------------------------
# airoha target patches + W1700K DTS + mt76 patches/Makefile. ImmortalWrt's
# own build core (config-6.18 / target.mk / image/*) stays official; synced
# patches that no longer apply cleanly are skipped with a warning, not fatal.
git -C "$FORK" fetch --depth=1 origin main:refs/remotes/origin/main 2>&- ||:
git -C "$FORK" sparse-checkout set \
    package/luci-app-wifi7 package/luci-app-mlo package/luci-app-airoha-npu \
    package/luci-app-airoha-flowsense package/luci-app-w1700k-fancontrol \
    target/linux/airoha package/kernel/mt76

sync_platform() {
    local DIR="$1" SKIP_RE="$2" F
    while IFS= read -r F; do
        [ -n "$F" ] || continue
        mkdir -p "$(dirname "$F")"
        if [ -f "$FORK/$F" ]; then
            cp -f "$FORK/$F" "$F"
            echo "platform sync: $F"
        else
            echo "WARN: platform file missing upstream: $F"
        fi
    done < <(git -C "$FORK" diff --name-status origin/main..ubi2 -- "$DIR" 2>&- | awk '$1 != "D" {print $2}' | grep -Ev "$SKIP_RE")
}

sync_platform "target/linux/airoha" 'config-6\.18$|target\.mk$|image/'
sync_platform "package/kernel/mt76" '^$'

# Pre-check synced patches; skip any that fail to apply (quilt applies them later).
while IFS= read -r P; do
    [ -n "$P" ] || continue
    if ! patch -d . -p1 --dry-run --forward < "$P" >/dev/null 2>&1; then
        echo "WARN: platform patch conflict, skipping: $P"
        rm -f "$P"
    fi
done < <(git -C "$FORK" diff --name-only origin/main..ubi2 -- \
    target/linux/airoha/patches-6.18 package/kernel/mt76/patches 2>&-)


# -------------------------------------------------
# Existing W1700K custom files
# -------------------------------------------------

# Attended sysupgrade follows the official snapshot: attendedsysupgrade-common
# and owut are built in (no LuCI interface), so no overview.js replacement or
# extra strings are applied here.

mkdir -p feeds/luci/modules/luci-mod-status/patches

mv $DK_PROFILE/patches/998-single-wiphy.patch \
    feeds/luci/modules/luci-mod-status/patches/998-single-wiphy.patch

if [ -d package/luci-app-wifi7 ] && [ -f $DK_PROFILE/patches/998-wifi7-i18n.patch ]; then
    patch -d package/luci-app-wifi7 -p1 --ignore-whitespace < $DK_PROFILE/patches/998-wifi7-i18n.patch
fi

if [ -d package/luci-app-w1700k-fancontrol ] && [ -f $DK_PROFILE/patches/998-fancontrol-i18n.patch ]; then
    patch -d package/luci-app-w1700k-fancontrol -p1 --ignore-whitespace < $DK_PROFILE/patches/998-fancontrol-i18n.patch
fi

if [ -d package/luci-app-airoha-npu ] && [ -f $DK_PROFILE/patches/998-npu-i18n.patch ]; then
    patch -d package/luci-app-airoha-npu -p1 --ignore-whitespace < $DK_PROFILE/patches/998-npu-i18n.patch
fi

if [ -d package/luci-app-airoha-flowsense ] && [ -f $DK_PROFILE/patches/998-flowsense-i18n.patch ]; then
    patch -d package/luci-app-airoha-flowsense -p1 --ignore-whitespace < $DK_PROFILE/patches/998-flowsense-i18n.patch
fi

# ImmortalWrt's luci-app-irqbalance was rewritten upstream: its view no
# longer contains the raw row.tail string, and the feed already ships a
# complete zh_Hans translation for the new UI. The legacy i18n patch and
# PO from the OpenWrt project are obsolete here and are intentionally
# skipped to avoid breaking the build or regressing translations.


# -------------------------------------------------
# Install latest Aurora LuCI theme
# -------------------------------------------------

echo "Installing latest Aurora LuCI theme..."

rm -rf package/luci-theme-aurora

if ! git clone \
    --depth=1 \
    https://github.com/eamonxg/luci-theme-aurora.git \
    package/luci-theme-aurora
then
    echo "ERROR: Failed to download Aurora theme!"
    exit 1
fi

if [ ! -f package/luci-theme-aurora/Makefile ]; then
    echo "ERROR: Aurora theme was downloaded, but Makefile is missing!"
    exit 1
fi

echo "Aurora theme installed successfully."


# -------------------------------------------------
# Install Aurora theme configuration app
# -------------------------------------------------

echo "Installing Aurora theme configuration app..."

rm -rf package/luci-app-aurora-config

if ! git clone \
    --depth=1 \
    https://github.com/eamonxg/luci-app-aurora-config.git \
    package/luci-app-aurora-config
then
    echo "ERROR: Failed to download Aurora theme configuration app!"
    exit 1
fi

if [ ! -f package/luci-app-aurora-config/Makefile ]; then
    echo "ERROR: Aurora theme configuration app was downloaded, but Makefile is missing!"
    exit 1
fi

echo "Aurora theme configuration app installed successfully."

# 修改 Aurora 菜单式样（默认侧边栏 + 小圆角）
TPL_DIR="package/luci-app-aurora-config/root/usr/share/aurora/"
if ls "$TPL_DIR"/*.template >/dev/null 2>&1; then
    sed -i "s/nav_type '.*'/nav_type 'sidebar'/g; s/struct_radius_base '.*'/struct_radius_base '0.125rem'/g" "$TPL_DIR"/*.template
    if grep -q "nav_type 'sidebar'" "$TPL_DIR"/*.template; then
        echo "theme-aurora nav preset applied!"
    else
        echo "theme-aurora nav preset failed; continuing!"
    fi
else
    echo "theme-aurora nav preset skipped (no templates); continuing!"
fi


# -------------------------------------------------
# Add Chinese translations for Airoha LuCI apps
# -------------------------------------------------

echo "Installing Chinese translations for Airoha LuCI apps..."

translation_targets=(
    "luci-app-airoha-flowsense|package/luci-app-airoha-flowsense"
    "luci-app-airoha-npu|package/luci-app-airoha-npu"
    "luci-app-w1700k-fancontrol|package/luci-app-w1700k-fancontrol"
    "luci-app-wifi7|package/luci-app-wifi7"
)

for translation_target in "${translation_targets[@]}"; do
    package_name="${translation_target%%|*}"
    target="${translation_target#*|}"
    translation="$DK_PROFILE/po/zh_Hans/${package_name}.po"

    if [ ! -d "$target" ]; then
        echo "ERROR: Translation target package is missing: $target"
        exit 1
    fi
    if [ ! -f "$translation" ]; then
        echo "ERROR: Translation file is missing: $translation"
        exit 1
    fi

    mkdir -p "$target/po/zh_Hans"
    cp -f "$translation" "$target/po/zh_Hans/${package_name}.po"
done

# luci-app-irqbalance ships its own zh_Hans translation in the ImmortalWrt
# luci feed (see note above), so no PO is copied from po/zh_Hans.

# Attended sysupgrade matches the official snapshot (attendedsysupgrade-common
# + owut, CLI only), so no custom attendedsysupgrade strings are appended.

# The temperature & fan overview widget ships as 15_temperature.js inside
# luci-mod-status. Core modules translate via luci-base's "base" domain, so
# append its strings to the upstream base.po for the Chinese UI.
BASE_PO="feeds/luci/modules/luci-base/po/zh_Hans/base.po"
if [ -f "$BASE_PO" ] && [ -f $DK_PROFILE/po/zh_Hans/base-custom.po ]; then
    cat $DK_PROFILE/po/zh_Hans/base-custom.po >> "$BASE_PO"
fi

# The upstream menu titles omit the vendor prefix. Keep the user-facing
# application names explicit without changing application behavior.
if [ -f package/luci-app-airoha-npu/root/usr/share/luci/menu.d/luci-app-airoha-npu.json ]; then
    sed -i 's/"title": "SoC Status"/"title": "Airoha SoC 状态"/' \
        package/luci-app-airoha-npu/root/usr/share/luci/menu.d/luci-app-airoha-npu.json
fi
if [ -d package/luci-app-airoha-flowsense ]; then
    find package/luci-app-airoha-flowsense -type f \( -name '*.json' -o -name '*.js' \) -exec \
        sed -i -e 's/"title": "FlowSense"/"title": "Airoha 流量传感器"/g' \
               -e 's/"title": "Airoha FlowSense"/"title": "Airoha 流量传感器"/g' {} +
fi

# Move Airoha Fan Control from the System menu into the Status menu, between
# Airoha SoC Status (npu) and Airoha FlowSense. The dispatcher types menu
# order as int, so use consecutive integers: npu 15, fan 16, flowsense 17.
if [ -f package/luci-app-w1700k-fancontrol/root/usr/share/luci/menu.d/luci-app-w1700k-fancontrol.json ]; then
    sed -i -e 's#admin/system/fan#admin/status/fan#g' \
           -e 's#"order": 90#"order": 16#' \
        package/luci-app-w1700k-fancontrol/root/usr/share/luci/menu.d/luci-app-w1700k-fancontrol.json
fi
if [ -f package/luci-app-airoha-flowsense/root/usr/share/luci/menu.d/luci-app-airoha-flowsense.json ]; then
    sed -i 's#"order": 16#"order": 17#' \
        package/luci-app-airoha-flowsense/root/usr/share/luci/menu.d/luci-app-airoha-flowsense.json
fi

echo "Airoha LuCI translations installed successfully."

# The package index is generated during feeds install, before these
# translation files existed. Drop the cached index so make defconfig
# rescans and registers the new luci-i18n-*-zh-cn packages.
rm -rf tmp/info 2>/dev/null || true
rm -f tmp/.packageinfo 2>/dev/null || true


# -------------------------------------------------
# Enable Chinese language
# -------------------------------------------------

echo "Enabling Chinese language..."

grep -qxF 'CONFIG_LUCI_LANG_zh_Hans=y' .config || \
    echo 'CONFIG_LUCI_LANG_zh_Hans=y' >> .config


# -------------------------------------------------
# Enable Aurora
# -------------------------------------------------

echo "Enabling Aurora theme..."

grep -qxF 'CONFIG_PACKAGE_luci-theme-aurora=y' .config || \
    echo 'CONFIG_PACKAGE_luci-theme-aurora=y' >> .config

grep -qxF 'CONFIG_PACKAGE_luci-app-aurora-config=y' .config || \
    echo 'CONFIG_PACKAGE_luci-app-aurora-config=y' >> .config


echo "=============================================="
echo "Custom commands completed"
