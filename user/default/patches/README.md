# 补丁来源

基于 [ImmortalWrt 官方 master](https://github.com/immortalwrt/immortalwrt) 及官方 feeds。构建环境使用本仓库维护的官方 Debian Dockerfile。以下为明确保留的本地补丁，不在构建时整批镜像 fork。

## 本地补丁

| 文件 | 用途与来源 |
| --- | --- |
| `745-*`、`746-*` | E2 PCS RX 校准、MDIO 识别前的 PHY 复位处理；来源 OpenWRT-fanboy/OpenW1700k `972634e64d19cba0095b662a0bfd9561ebef635c` 的 `target/linux/airoha/patches-6.18/` |
| `999-net-phy-realtek-rtl8261ce.patch`、`../tree/target/linux/generic/files/drivers/net/phy/rtl8261ce/` | RTL8261CE 驱动与 Kconfig/Makefile 接入，源自 OpenW1700k 的 Jihong Min 实现；支持 PHY ID `0x001cc890` 的硬件变体，不替代官方 RTL8261N 驱动 |
| `910-mt76-*`、`911-mt76-*` | OpenW1700k 无线固件功率限制启用与刷新的本地适配，仅保留这两个 mt76 定制补丁 |
| `610-w1700k-us-power-30.patch` | 在官方 regdb 补丁基础上追加本项目 US 30 dBm 配置 |
| `999-fix-txpower-list.patch` | iwinfo 功率列表展示，来源上述 `972634e...` 的 `package/network/utils/iwinfo/patches/` |
| `940-pmdomain-airoha-cpu-pll-fallback.patch`、`002-w1700k-cpufreq-resources.patch` | 标准 CPUFreq 兼容，来源上述 `972634e...` 的 940 C 代码及 W1700K 设备树资源；不重复引入 Kconfig，保留官方 attach_list、0–14 状态、500–1200 MHz 与调频策略，不超频 |
| `998-single-wiphy.patch` | single-wiphy 无线设备的 LuCI 状态适配，仅涉及界面 |

## 维护原则

- 非必要不加补丁；官方已有功能和特性以官方实现为准。
- 新修复先核对来源、适用性及官方是否已包含；官方吸收后验证并移除本地重复补丁。
- 必要补丁应用失败必须停止构建，不跳过错误继续打包。
- NAND 保持官方 50 MHz，不恢复 OC、额外网桥 flowtable、GRO/NPU 扩展、ramoops、mt76 统计/txfree 及 hostapd/Dropbear 等 fork 定制。
- 保留中文 LuCI、Aurora、专属应用、WOL、ttyd、既定访问与无线设置，以及启动绿灯、故障红灯、运行白灯。
- 频率设置入口按实际硬件能力显示，不伪造读数；标准 CPUFreq 兼容补丁恢复原有数据路径。
- 旧网桥脚本仅保留配置迁移清理，运行行为由官方 fw4 与网络栈负责。

当前方案已通过用户实机测试，原失联问题已解决。该反馈不等于逐项硬件机制或射频功率测量；后续滚动更新仍需核对补丁兼容性。
