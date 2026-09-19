#!/bin/bash

set -e

echo "=============================================="
echo "Running custom commands"

# -------------------------------------------------
# Fetch W1700K LuCI apps from user's packages repo
# -------------------------------------------------
# luci-app-wifi7 / luci-app-airoha-npu /
# luci-app-airoha-flowsense / luci-app-airoha-fancontrol
# are maintained in yahuisme/packages with native LuCI UI,
# built-in 100% i18n, and strict platform safety checks.
PKG_REPO=/tmp/yahuisme-packages
if ! git clone --depth=1 https://github.com/yahuisme/packages.git "$PKG_REPO"; then
    echo "ERROR: Failed to clone user packages repo!"
    exit 1
fi
cp -r "$PKG_REPO/luci-app-wifi7" "$PKG_REPO/luci-app-airoha-npu" \
      "$PKG_REPO/luci-app-airoha-flowsense" \
      "$PKG_REPO/luci-app-airoha-fancontrol" package/

# Explicit, reviewed local hardware delta; no build-time donor mirror.
for patch in 745-net-pcs-airoha-extend-manual-rx-calib-to-E2-silicon.patch \
             746-net-dsa-mt7530-pre-deassert-phy-reset-gpios-before-mdio-scan.patch \
             940-pmdomain-airoha-cpu-pll-fallback.patch; do
    cp -f "$DK_PROFILE/patches/$patch" target/linux/airoha/patches-6.18/
done
patch -p1 --fuzz=0 < "$DK_PROFILE/patches/002-w1700k-cpufreq-resources.patch"
mkdir -p package/network/utils/iwinfo/patches
cp -f "$DK_PROFILE/patches/999-fix-txpower-list.patch" package/network/utils/iwinfo/patches/

# -------------------------------------------------
# Existing W1700K custom files
# -------------------------------------------------

mkdir -p feeds/luci/modules/luci-mod-status/patches
cp -f "$DK_PROFILE/patches/998-single-wiphy.patch" \
    feeds/luci/modules/luci-mod-status/patches/998-single-wiphy.patch

# Only the two required firmware power-limit changes, never a broad mirror.
mkdir -p package/kernel/mt76/patches
cp -f "$DK_PROFILE/patches/910-mt76-mt7996-enable-firmware-txpower-limit.patch" \
    "$DK_PROFILE/patches/911-mt76-mt7996-refresh-power-limits-on-txpower-changes.patch" \
    package/kernel/mt76/patches/
echo "mt76: official package + two power-limit patches"

cp -f "$DK_PROFILE/patches/999-net-phy-realtek-rtl8261ce.patch" \
    target/linux/generic/hack-6.18/
echo "kernel: rtl8261ce PHY patch installed"

# rtl8261ce driver files + fork tree files cannot reach target/linux/...
# or package/... via the rootfs files/ overlay, so copy them into the
# buildroot tree explicitly (same paths as the OpenW1700k fork).
TREE="$DK_PROFILE/tree"
mkdir -p target/linux/generic/files/drivers/net/phy/rtl8261ce
cp -f "$TREE"/target/linux/generic/files/drivers/net/phy/rtl8261ce/* \
    target/linux/generic/files/drivers/net/phy/rtl8261ce/
if [ ! -f target/linux/generic/files/drivers/net/phy/rtl8261ce/Kconfig ]; then
    echo "ERROR: rtl8261ce driver files missing after injection; abort" >&2
    exit 1
fi
echo "rtl8261ce: driver files injected into target/linux/generic/files"
# -------------------------------------------------
# rtl8261ce kmod definition (fork netdevices.mk mirror)
# -------------------------------------------------
NDM=package/kernel/linux/modules/netdevices.mk
if ! grep -q 'phy-rtl8261ce' "$NDM"; then
    cat >> "$NDM" <<'EOF'

define KernelPackage/phy-rtl8261ce
   SUBMENU:=$(NETWORK_DEVICES_MENU)
   TITLE:=Realtek RTL8261CE 10GBASE-T PHY driver
   KCONFIG:=CONFIG_RTL8261CE_PHY
   DEPENDS:=+kmod-libphy +kmod-hwmon-core
   FILES:=$(LINUX_DIR)/drivers/net/phy/rtl8261ce/rtk-rtl8261ce-phy.ko
   AUTOLOAD:=$(call AutoLoad,18,rtk-rtl8261ce-phy,1)
endef

define KernelPackage/phy-rtl8261ce/description
   Supports the Realtek RTL8261CE 10GBASE-T PHY.
endef

$(eval $(call KernelPackage,phy-rtl8261ce))
EOF
    echo "netdevices.mk: phy-rtl8261ce kmod added"
fi

# -------------------------------------------------
# Wireless fixes (quilt-applied)
# 610 US power boost (self-maintained, applied after official 500/600):
#   5.5G 30dBm DFS / 5.8G 5730-5895@160 30dBm (UNII-4 merged) /
#   6G 30dBm no NO-IR. Matches the w1700k-openwrt regdb outcome
#   (CN 2.4G/5.2G + US 5.2G already covered by official 600 patch).
# 999 iwinfo txpower list (locally audited copy)
# -------------------------------------------------
mkdir -p package/firmware/wireless-regdb/patches
mkdir -p package/network/utils/iwinfo/patches

if [ -f "$DK_PROFILE/patches/610-w1700k-us-power-30.patch" ]; then
    cp -f "$DK_PROFILE/patches/610-w1700k-us-power-30.patch" package/firmware/wireless-regdb/patches/
    echo "regdb patch: 610-w1700k-us-power-30.patch"
else
    echo "ERROR: regdb patch missing: 610-w1700k-us-power-30.patch" >&2
    exit 1
fi
# Preserve the user's status LED colors, not donor platform enhancements.
DTS=target/linux/airoha/dts/an7581-w1700k-ubi.dts
sed -i -e 's/led-boot = &led_status_red;/led-boot = \&led_status_green;/' \
       -e 's/led-failsafe = &led_status_blue;/led-failsafe = \&led_status_red;/' \
       -e 's/led-running = &led_status_green;/led-running = \&led_status_white;/' "$DTS"
for alias in 'boot green' 'failsafe red' 'running white'; do
    read -r state color <<< "$alias"
    grep -q "led-$state = &led_status_$color;" "$DTS" || { echo "ERROR: LED alias mismatch: $state" >&2; exit 1; }
done

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
TPL_DIR="package/luci-app-aurora-config/root/usr/share/aurora"
[ -f "$TPL_DIR/default.template" ] || { echo "ERROR: Aurora default template missing" >&2; exit 1; }
for tpl in "$TPL_DIR"/*.template; do
    sed -i "s/nav_type '.*'/nav_type 'sidebar'/g; s/struct_radius_base '.*'/struct_radius_base '0.125rem'/g" "$tpl"
    if ! grep -q "^[[:space:]]*option nav_type 'sidebar'[[:space:]]*$" "$tpl" \
        || ! grep -q "^[[:space:]]*option struct_radius_base '0\.125rem'[[:space:]]*$" "$tpl"; then
        echo "ERROR: Aurora preset template mismatch: $tpl" >&2
        exit 1
    fi
done
echo "theme-aurora nav preset applied!"


# -------------------------------------------------
# Add Chinese translations for overview temperature widget
# -------------------------------------------------

# The temperature & fan overview widget ships as 15_temperature.js inside
# luci-mod-status. Core modules translate via luci-base's "base" domain, so
# append its strings to the upstream base.po for the Chinese UI.
BASE_PO="feeds/luci/modules/luci-base/po/zh_Hans/base.po"
if [ -f "$BASE_PO" ] && [ -f "$DK_PROFILE/po/zh_Hans/base-custom.po" ]; then
    cat "$DK_PROFILE/po/zh_Hans/base-custom.po" >> "$BASE_PO"
fi

echo "Airoha LuCI configuration completed."

# Feeds install indexed packages before the custom apps, theme and PHY
# recipe were injected. Drop the index so make defconfig discovers them
# and their built-in luci-i18n-*-zh-cn packages.
rm -rf tmp/info 2>/dev/null || true
rm -f tmp/.packageinfo 2>/dev/null || true

echo "=============================================="
echo "Custom commands completed"
