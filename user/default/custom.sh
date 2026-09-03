#!/bin/bash

set -e

echo "=============================================="
echo "Running custom commands"

# -------------------------------------------------
# Fetch W1700K-specific packages and patches from OpenW1700k
# -------------------------------------------------
# luci-app-wifi7 / luci-app-mlo / luci-app-airoha-npu /
# luci-app-airoha-flowsense / luci-app-w1700k-fancontrol
# are not available in ImmortalWrt feeds. Platform / iwinfo patches are
# also taken from the fork at build time so they always track upstream
# latest (same model as the w1700k-openwrt builds that use the fork
# tree directly). Follow the OpenW1700k ubi2 branch at build time
# (no version pinning). mt76 stays on the ImmortalWrt official package
# with ported fork patches (see below).
FORK=/tmp/openw1700k
if ! git clone --depth=1 --filter=blob:none --sparse --branch ubi2 \
    https://github.com/OpenWRT-fanboy/OpenW1700k.git "$FORK"; then
    echo "ERROR: Failed to clone OpenW1700k fork!"
    exit 1
fi
git -C "$FORK" sparse-checkout set \
    package/luci-app-wifi7 package/luci-app-mlo package/luci-app-airoha-npu \
    package/luci-app-airoha-flowsense package/luci-app-w1700k-fancontrol \
    target/linux/airoha/patches-6.18 \
    package/network/utils/iwinfo/patches
cp -r "$FORK/package/luci-app-wifi7" "$FORK/package/luci-app-mlo" \
      "$FORK/package/luci-app-airoha-npu" "$FORK/package/luci-app-airoha-flowsense" \
      "$FORK/package/luci-app-w1700k-fancontrol" package/


# -------------------------------------------------
# Existing W1700K custom files
# -------------------------------------------------

mkdir -p feeds/luci/modules/luci-mod-status/patches

cp -f $DK_PROFILE/patches/998-single-wiphy.patch \
    feeds/luci/modules/luci-mod-status/patches/998-single-wiphy.patch

if [ ! -d package/luci-app-wifi7 ]; then
    echo "ERROR: luci-app-wifi7 missing after fork clone" >&2
    exit 1
fi
if [ ! -f $DK_PROFILE/patches/998-wifi7-i18n.patch ]; then
    echo "ERROR: 998-wifi7-i18n.patch missing" >&2
    exit 1
fi
patch -d package/luci-app-wifi7 -p1 --ignore-whitespace < $DK_PROFILE/patches/998-wifi7-i18n.patch

if [ ! -d package/luci-app-w1700k-fancontrol ]; then
    echo "ERROR: luci-app-w1700k-fancontrol missing after fork clone" >&2
    exit 1
fi
if [ ! -f $DK_PROFILE/patches/998-fancontrol-i18n.patch ]; then
    echo "ERROR: 998-fancontrol-i18n.patch missing" >&2
    exit 1
fi
patch -d package/luci-app-w1700k-fancontrol -p1 --ignore-whitespace < $DK_PROFILE/patches/998-fancontrol-i18n.patch

if [ ! -d package/luci-app-airoha-npu ]; then
    echo "ERROR: luci-app-airoha-npu missing after fork clone" >&2
    exit 1
fi
if [ ! -f $DK_PROFILE/patches/998-npu-i18n.patch ]; then
    echo "ERROR: 998-npu-i18n.patch missing" >&2
    exit 1
fi
patch -d package/luci-app-airoha-npu -p1 --ignore-whitespace < $DK_PROFILE/patches/998-npu-i18n.patch

if [ ! -d package/luci-app-airoha-flowsense ]; then
    echo "ERROR: luci-app-airoha-flowsense missing after fork clone" >&2
    exit 1
fi
if [ ! -f $DK_PROFILE/patches/998-flowsense-i18n.patch ]; then
    echo "ERROR: 998-flowsense-i18n.patch missing" >&2
    exit 1
fi
patch -d package/luci-app-airoha-flowsense -p1 --ignore-whitespace < $DK_PROFILE/patches/998-flowsense-i18n.patch

# -------------------------------------------------
# SPI-NAND stability: 50MHz -> 33MHz (OpenW1700k fix)
# -------------------------------------------------
if grep -q 'spi-max-frequency = <50000000>' target/linux/airoha/dts/an7581.dtsi 2>/dev/null; then
    sed -i 's/spi-max-frequency = <50000000>/spi-max-frequency = <33000000>/' \
        target/linux/airoha/dts/an7581.dtsi
    if grep -q 'spi-max-frequency = <33000000>' target/linux/airoha/dts/an7581.dtsi; then
        echo "spi-nand clock lowered to 33MHz"
    else
        echo "ERROR: spi-nand clock sed did not match; abort" >&2
        exit 1
    fi
elif grep -q 'spi-max-frequency = <33000000>' target/linux/airoha/dts/an7581.dtsi 2>/dev/null; then
    echo "spi-nand clock already 33MHz"
else
    echo "WARN: spi-max-frequency not found in an7581.dtsi; skip"
fi

# -------------------------------------------------
# W1700K platform fixes from OpenW1700k (quilt-applied)
# 745 pcs E2 calib / 746 mt7530 reset / 916-02 GRO_HW /
# 992-20 stability / 117-03 npu timeout / 992-21 npu init stability /
# 910-02 usb-pcie clk /
# 939 SMCCC cpufreq / 940 CPU pmdomain (PLL fallback) /
# 998 log silence / 9990 hw gro state
# Copied from the fork at build time to track upstream latest.
# -------------------------------------------------
for p in 745-net-pcs-airoha-extend-manual-rx-calib-to-E2-silicon.patch \
         746-net-dsa-mt7530-pre-deassert-phy-reset-gpios-before-mdio-scan.patch \
         916-02-net-airoha-Implement-HW-GRO-TCP-support.patch \
         992-20-net-airoha-stability.patch \
         992-21-net-airoha-npu-init-stability.patch \
         117-03-airoha_npu_eagle_add_ser.patch \
         910-02-usb-pcie.patch \
         939-cpufreq-airoha-Add-EN7581-CPUFreq-SMCCC-driver.patch \
         940-pmdomain-airoha-Add-Airoha-CPU-PM-Domain-support.patch \
         998-silence-PHY-LED-pinctrl-error.patch \
         9990-net-airoha-share-hw-gro-state-across-qdma-users.patch; do
    if [ -f "$FORK/target/linux/airoha/patches-6.18/$p" ]; then
        cp -f "$FORK/target/linux/airoha/patches-6.18/$p" target/linux/airoha/patches-6.18/
        echo "platform patch: $p"
    else
        echo "ERROR: patch not found in OpenW1700k fork: $p"
        exit 1
    fi
done

# -------------------------------------------------
# mt76: ImmortalWrt official package + mirrored fork patches
# -------------------------------------------------
# Keep ImmortalWrt's official mt76 (openwrt/mt76 @ 59676919). The fork's
# snapshot (01367e60) requires kernel 7.x mac80211 API and does not build
# on the 6.18 backport, so mirror the fork's own mt76 patches on top of
# the official package instead. They apply after the official 100 patch;
# a failed apply aborts the build (fail-closed).
mkdir -p package/kernel/mt76/patches
mt76_patches=("$DK_PROFILE"/patches/9??-mt76-*.patch)
if [ "${mt76_patches[0]}" = "$DK_PROFILE/patches/9??-mt76-*.patch" ]; then
    echo "ERROR: no mt76 patches found in $DK_PROFILE/patches (9??-mt76-*.patch)"
    exit 1
fi
for p in "${mt76_patches[@]}"; do
    cp -f "$p" package/kernel/mt76/patches/
done
echo "mt76: official package + ${#mt76_patches[@]} mirrored fork patches"

# -------------------------------------------------
# wifi-scripts: per-interface txpower (fork pr-23990 mirror)
# -------------------------------------------------
# The fork carries pr-23990 (per-VIF txpower with verify+retry) on top
# of openwrt wifi-scripts; mirror it onto ImmortalWrt's ucode script.
WS_PATCH="$DK_PROFILE/patches/910-wifi-scripts-set-txpower-per-interface.patch"
if [ -f "$WS_PATCH" ]; then
    patch -p1 --ignore-whitespace < "$WS_PATCH"
    echo "wifi-scripts: per-interface txpower patch applied"
else
    echo "ERROR: wifi-scripts txpower patch missing"
    exit 1
fi

# -------------------------------------------------
# hostapd: 6G band does not require DFS (fork mtk-0015 mirror)
# -------------------------------------------------
cp -f "$DK_PROFILE/patches/810-hostapd-6g-band-does-not-require-dfs.patch" \
    package/network/services/hostapd/patches/
echo "hostapd: 6G-no-DFS patch installed"

# -------------------------------------------------
# dropbear: quiet per-connection session logs (fork mirror)
# -------------------------------------------------
cp -f "$DK_PROFILE/patches/500-quiet-session-logs.patch" \
    package/network/services/dropbear/patches/
echo "dropbear: quiet session logs patch installed"

# -------------------------------------------------
# Kernel: bridge flow offload + rtl8261ce PHY (fork mirror)
# -------------------------------------------------
cp -f "$DK_PROFILE"/patches/675-0[123]-*.patch target/linux/generic/pending-6.18/
cp -f "$DK_PROFILE/patches/999-net-phy-realtek-rtl8261ce.patch" \
    target/linux/generic/hack-6.18/
echo "kernel: bridge flow offload + rtl8261ce PHY patches installed"

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

mkdir -p target/linux/airoha/base-files/etc
cp -f "$TREE/target/linux/airoha/base-files/etc/tx-debug.sh" \
    target/linux/airoha/base-files/etc/
mkdir -p target/linux/airoha/an7581/base-files/etc/hotplug.d/iface
cp -f "$TREE/target/linux/airoha/an7581/base-files/etc/hotplug.d/iface/51-bridge-flow-offload" \
    target/linux/airoha/an7581/base-files/etc/hotplug.d/iface/
mkdir -p package/network/config/bridge-flow-offload/files/usr/share/bridge-flow-offload
cp -f "$TREE/package/network/config/bridge-flow-offload/Makefile" \
    package/network/config/bridge-flow-offload/
cp -f "$TREE/package/network/config/bridge-flow-offload/files/usr/share/bridge-flow-offload/apply-rules.sh" \
    package/network/config/bridge-flow-offload/files/usr/share/bridge-flow-offload/
# verify all tree injections landed (fail closed)
for f in \
    target/linux/generic/files/drivers/net/phy/rtl8261ce/Kconfig \
    target/linux/airoha/base-files/etc/tx-debug.sh \
    target/linux/airoha/an7581/base-files/etc/hotplug.d/iface/51-bridge-flow-offload \
    package/network/config/bridge-flow-offload/Makefile; do
    [ -f "$f" ] || { echo "ERROR: tree injection missing: $f; abort" >&2; exit 1; }
done
echo "tree: airoha base-files + bridge-flow-offload package injected"

# -------------------------------------------------
# ramoops/pstore: crash log region (fork mirror)
# -------------------------------------------------
patch -p1 --ignore-whitespace < "$DK_PROFILE/patches/910-airoha-ramoops.patch"
for cfg in CONFIG_PSTORE=y CONFIG_PSTORE_COMPRESS=y CONFIG_PSTORE_CONSOLE=y \
           CONFIG_PSTORE_PMSG=y CONFIG_PSTORE_RAM=y; do
    grep -qxF "$cfg" target/linux/airoha/an7581/config-6.18 \
        || echo "$cfg" >> target/linux/airoha/an7581/config-6.18
done
echo "ramoops: dts node + PSTORE config enabled"

# -------------------------------------------------
# AN7581 audio: disable (no audio hardware on W1700K; fork mirror)
# -------------------------------------------------
if grep -q '^CONFIG_SND_SOC_AN7581=y$' target/linux/airoha/an7581/config-6.18; then
    sed -i 's/^CONFIG_SND_SOC_AN7581=y$/# CONFIG_SND_SOC_AN7581 is not set/' \
        target/linux/airoha/an7581/config-6.18
    grep -q '^# CONFIG_SND_SOC_AN7581 is not set$' \
        target/linux/airoha/an7581/config-6.18 \
        && echo "AN7581 audio: disabled (fork mirror)" \
        || { echo "ERROR: AN7581 audio disable failed"; exit 1; }
else
    echo "AN7581 audio: already disabled or absent"
fi

# -------------------------------------------------
# Default packages: eip93 crypto + bridge-flow-offload (fork target.mk mirror)
# -------------------------------------------------
TMK=target/linux/airoha/an7581/target.mk
if grep -q 'kmod-crypto-hw-eip93' "$TMK"; then
    echo "target.mk: eip93/flow-offload already present"
else
    sed -i 's#\tairoha-en7581-npu-firmware uboot-envtools#\tairoha-en7581-npu-firmware uboot-envtools kmod-crypto-hw-eip93 \\\n\tbridge-flow-offload#' "$TMK"
    if grep -q 'kmod-crypto-hw-eip93' "$TMK" && grep -q 'bridge-flow-offload' "$TMK"; then
        echo "target.mk: +kmod-crypto-hw-eip93 +bridge-flow-offload"
    else
        echo "ERROR: target.mk sed did not match; abort"
        exit 1
    fi
fi

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

# Enable the RTL8261CE PHY driver in the W1700K DEVICE_PACKAGES (fork
# an7581.mk ships `rtl826x-firmware kmod-phy-rtl8261ce`; ImmortalWrt's
# own an7581.mk stops at rtl826x-firmware). Without this the driver is
# defined but never selected, and the firmware misses 10G PHY support.
ANM=target/linux/airoha/image/an7581.mk
if grep -q 'rtl826x-firmware kmod-phy-rtl8261ce' "$ANM"; then
    echo "an7581.mk: kmod-phy-rtl8261ce already in W1700K DEVICE_PACKAGES"
elif grep -q 'rtl826x-firmware' "$ANM"; then
    sed -i 's/rtl826x-firmware$/rtl826x-firmware kmod-phy-rtl8261ce/' "$ANM"
    if grep -q 'rtl826x-firmware kmod-phy-rtl8261ce' "$ANM"; then
        echo "an7581.mk: +kmod-phy-rtl8261ce in W1700K DEVICE_PACKAGES"
    else
        echo "ERROR: an7581.mk sed did not match; abort" >&2
        exit 1
    fi
else
    echo "WARN: rtl826x-firmware not found in $ANM; skip"
fi

# -------------------------------------------------
# Wireless fixes (quilt-applied)
# 610 US power boost (self-maintained, applied after official 500/600):
#   5.5G 30dBm DFS / 5.8G 5730-5895@160 30dBm (UNII-4 merged) /
#   6G 30dBm no NO-IR. Matches the w1700k-openwrt regdb outcome
#   (CN 2.4G/5.2G + US 5.2G already covered by official 600 patch).
# 999 iwinfo txpower list (from the fork at build time)
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

if [ -f "$FORK/package/network/utils/iwinfo/patches/999-fix-txpower-list.patch" ]; then
    cp -f "$FORK/package/network/utils/iwinfo/patches/999-fix-txpower-list.patch" package/network/utils/iwinfo/patches/
    echo "iwinfo patch: 999-fix-txpower-list.patch"
else
    echo "ERROR: patch not found in OpenW1700k fork: 999-fix-txpower-list.patch"
    exit 1
fi

# -------------------------------------------------
# OC overclock: CPU OPP to 1.4GHz (ubi2-oc profile only)
# Triggered by performance governor in config.diff
# -------------------------------------------------
if grep -q '^CONFIG_CPU_FREQ_DEFAULT_GOV_PERFORMANCE=y' .config 2>/dev/null; then
    if [ -f "$DK_PROFILE/patches/001-oc-cpu-opp-1400mhz.patch" ]; then
        patch -p1 --ignore-whitespace \
            < "$DK_PROFILE/patches/001-oc-cpu-opp-1400mhz.patch"
        echo "OC OPP patch applied (1.4GHz)"
    else
        echo "ERROR: OC profile but OPP patch missing; abort" >&2
        exit 1
    fi
fi

# -------------------------------------------------
# LED status colors (follow OpenW1700k: boot=green, failsafe=red, running=white)
# -------------------------------------------------
DTS=target/linux/airoha/dts/an7581-w1700k-ubi.dts
if grep -q 'led-boot = &led_status_red;' "$DTS" 2>/dev/null; then
    sed -i -e 's/led-boot = &led_status_red;/led-boot = \&led_status_green;/' \
           -e 's/led-failsafe = &led_status_blue;/led-failsafe = \&led_status_red;/' \
           -e 's/led-running = &led_status_green;/led-running = \&led_status_white;/' \
        "$DTS"
    if grep -q 'led-boot = &led_status_green;' "$DTS" \
        && grep -q 'led-failsafe = &led_status_red;' "$DTS" \
        && grep -q 'led-running = &led_status_white;' "$DTS"; then
        echo "LED status colors set (boot=green, failsafe=red, running=white)"
    else
        echo "ERROR: LED colors sed did not match; abort" >&2
        exit 1
    fi
else
    echo "WARN: LED aliases not found in an7581-w1700k-ubi.dts; skip"
fi

# -------------------------------------------------
# CPUFreq: add SCU/MCUCFG register ranges to the cpufreq node
# -------------------------------------------------
# The Airoha CPU PM domain driver needs the chip-scu/mcucfg ranges for
# its PLL fallback path (W1700K ATF lacks the AVS SMC handler).
# OpenW1700k carries these regs in an7581.dtsi; add them if absent.
DTSI=target/linux/airoha/dts/an7581.dtsi
if grep -q 'reg-names = "chip-scu", "mcucfg"' "$DTSI" 2>/dev/null; then
    echo "cpufreq node regs already present"
elif grep -q '^[[:space:]]*cpufreq: cpufreq {' "$DTSI" 2>/dev/null; then
    sed -i '/^[[:space:]]*cpufreq: cpufreq {$/a\
\t\treg = <0x0 0x1fa20000 0x0 0x2c0>, <0x0 0x1efbe000 0x0 0x800>;\
\t\treg-names = "chip-scu", "mcucfg";' "$DTSI"
    if grep -q 'reg-names = "chip-scu", "mcucfg"' "$DTSI"; then
        echo "cpufreq node regs added (chip-scu/mcucfg)"
    else
        echo "ERROR: cpufreq regs injection failed; abort" >&2
        exit 1
    fi
else
    echo "WARN: cpufreq node not found in an7581.dtsi; skip"
fi

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
        sed -i -e 's/"title": "FlowSense"/"title": "Airoha 流量感知"/g' \
               -e 's/"title": "Airoha FlowSense"/"title": "Airoha 流量感知"/g' {} +
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

# Move ttyd from the System menu into Services, directly below the
# irqbalance app (order 90). Only the menu keys and the parent order
# change; the view paths stay untouched.
TTYD_MENU="feeds/luci/applications/luci-app-ttyd/root/usr/share/luci/menu.d/luci-app-ttyd.json"
if [ -f "$TTYD_MENU" ]; then
    sed -i 's#admin/system/ttyd#admin/services/ttyd#g' "$TTYD_MENU"
    sed -i 's/^\([[:space:]]*"admin\/services\/ttyd": {\)$/\1\
    "order": 91,/' "$TTYD_MENU"
    if grep -q '"admin/services/ttyd"' "$TTYD_MENU" && grep -q '"order": 91,' "$TTYD_MENU"; then
        echo "ttyd menu moved to Services (order 91)"
    else
        echo "WARN: ttyd menu sed did not match; skip"
    fi
else
    echo "WARN: ttyd menu file not found; skip"
fi

# luci-app-irqbalance ships its own zh_Hans translation in the
# feed. The feed PO leaves the menu title "irqbalance" untranslated and the
# view leaves raw /proc/interrupts IPI names unlocalized. Apply our i18n patch
# and append the interrupt names to the feed PO.
IRQ_DIR="feeds/luci/applications/luci-app-irqbalance"
if [ -d "$IRQ_DIR" ] && [ -f "$DK_PROFILE/patches/998-irqbalance-i18n.patch" ]; then
    patch -d "$IRQ_DIR" -p1 --ignore-whitespace < "$DK_PROFILE/patches/998-irqbalance-i18n.patch"
    echo "irqbalance: IPI interrupt names translation patch applied"
fi

IRQ_PO="$IRQ_DIR/po/zh_Hans/irqbalance.po"
if [ -f "$IRQ_PO" ]; then
    sed -i '/^msgid "irqbalance"$/{n;s/^msgstr "irqbalance"$/msgstr "IRQ 平衡"/}' "$IRQ_PO"
    if grep -q 'msgstr "IRQ 平衡"' "$IRQ_PO"; then
        echo "irqbalance menu title localized (IRQ 平衡)"
    else
        echo "WARN: irqbalance zh_Hans msgid not found; skip"
    fi
    cat >> "$IRQ_PO" << 'EOF'

msgid "Rescheduling interrupts"
msgstr "重新调度中断"

msgid "Function call interrupts"
msgstr "函数调用中断"

msgid "CPU stop interrupts"
msgstr "CPU 停止中断"

msgid "CPU stop NMIs"
msgstr "CPU 停止 NMI"

msgid "Timer broadcast interrupts"
msgstr "定时器广播中断"

msgid "IRQ work interrupts"
msgstr "IRQ 工作中断"

msgid "CPU backtrace interrupts"
msgstr "CPU 回溯中断"

msgid "KGDB roundup interrupts"
msgstr "KGDB 汇总中断"
EOF
    echo "irqbalance IPI interrupt names added to PO"
else
    echo "WARN: irqbalance zh_Hans PO not found; skip"
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
