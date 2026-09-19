# Local delta on official ImmortalWrt master

Rolling source and both feeds remain official. These files are reviewed local copies, not a build-time fork mirror. Recheck application and necessity when upstream changes; mandatory failures must stop preparation.

| File / tree | Purpose / source |
|---|---|
| `745-*`, `746-*` | E2 PCS RX calibration and PHY reset before MDIO scan; copied verbatim from OpenWRT-fanboy/OpenW1700k `972634e64d19cba0095b662a0bfd9561ebef635c`, `target/linux/airoha/patches-6.18/` |
| `999-net-phy-realtek-rtl8261ce.patch`, `../tree/target/linux/generic/files/drivers/net/phy/rtl8261ce/` | Existing RTL8261CE vendor driver and Kconfig/Makefile integration, originating from OpenW1700k (Jihong Min); retained for the `0x001cc890` hardware variant, not a substitute for official RTL8261N support |
| `910-mt76-*`, `911-mt76-*` | Existing locally mirrored OpenW1700k firmware power-limit enable/refresh support; only these two mt76 changes retained |
| `610-w1700k-us-power-30.patch` | Existing project-maintained US regdb 30 dBm configuration on top of ImmortalWrt's official regdb patches |
| `999-fix-txpower-list.patch` | iwinfo power-list presentation; copied from the same `972634e...` donor revision, `package/network/utils/iwinfo/patches/` |
| `998-single-wiphy.patch` | Existing LuCI status adaptation for single-wiphy radios (UI only) |

NAND remains at official 50 MHz: no reproduced failure justifies the inherited 33 MHz downclock. RTL8261CE is retained for the supported W1700K board variant, not as proof this physical unit uses it. Aurora, Chinese translations, WiFi7, Airoha NPU, FlowSense, fancontrol, WOL, the ttyd web terminal and Usteer remain separate UI customizations; existing access credentials/defaults are unchanged. Frequency menus/forms are hidden without CPUFreq/Devfreq interfaces, rather than restoring fork kernel extensions.

Removed: OC/CPUFreq/PLL changes, bridge flowtable and its hotplug producers, GRO/NPU extensions, ramoops, auxiliary mt76 statistics/txfree patches, hostapd/dropbear and audio fork tweaks. Existing LED colors (boot green, failsafe red, running white) are retained as user-visible customization. Official fw4 and network stack own runtime behavior. Retained-config migration only deletes obsolete bridge include/hotplug files; legacy network sysctls are unchanged.

Source preparation verified against official `f44d1535b4ef107a4ee255caa43cf101daf9fa35`: complete 579-patch kernel chain with overlays, and 8 official+local mt76/iwinfo/regdb patches. This is not compilation, RF measurement or device validation. 30 dBm remains an explicit user requirement; observe local radio regulations.
