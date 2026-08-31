# AI 协力构建的 Quantum Fiber W1700K ImmortalWrt 固件

适用于 **Quantum Fiber W1700K** 路由器的定制 ImmortalWrt 固件构建项目。

基于 [w1700k/builds](https://github.com/w1700k/builds) 构建框架，源码基线为 [ImmortalWrt 官方 snapshot](https://github.com/immortalwrt/immortalwrt)，内置应用、配置与汉化与 [w1700k-openwrt](https://github.com/yahuisme/w1700k-openwrt) 保持一致（值守式系统升级界面除外）。

> ⚠️ **仅适用于 Quantum Fiber W1700K，请勿刷入其他型号设备。**

---

## ✨ 主要特性

- 📝 内置专属应用已添加中文汉化
- 🎨 默认 Aurora LuCI 主题
- 🕐 系统时区：香港（UTC+8）
- 🌡️ LuCI 首页增加设备温度及风扇转速显示

---

## 📦 固件版本

| 固件 | 说明 |
| --- | --- |
| `ubi2` | 常规版本，使用标准 CPU 工作参数 |
| `ubi2-oc` | 超频版本，默认性能模式并超频 +200 MHz |

---

## 默认访问

- 管理地址：`192.168.8.1`
- 管理密码：无
- Wi-Fi SSID：`W1700K`
- Wi-Fi 密码：`12345678`

---

## 📡 默认无线配置

| 项目 | 2.4 GHz | 5 GHz | 6 GHz |
| --- | --- | --- | --- |
| 状态 | 开启 | 开启 | **关闭** |
| 区域 | US | US | US |
| 信道 | 1 | 36 | 37 |
| 频宽 / 模式 | Wi‑Fi 7（EHT20） | Wi‑Fi 7（EHT160） | Wi‑Fi 7（EHT320） |
| SSID | `W1700K` | `W1700K` | `W1700K-6G` |
| 加密 | WPA2-PSK | WPA2-PSK | WPA3-SAE |
| 密码 | `12345678` | `12345678` | `12345678` |
| 发射功率 | 23 dBm | 23 dBm | 23 dBm |

---

## 🌡️ 温度监控

LuCI 状态首页显示 CPU、主板、10G WAN/LAN PHY、2.4/5/6 GHz WiFi 温度及风扇转速/占空比，随温度区间变色提示。

---

## 🔄 自动构建

GitHub Actions 每日 **香港时间 17:00** 自动构建：

```text
W1700K-Immortalwrt_<构建时间>_r<版本号>
W1700K-OC-Immortalwrt_<构建时间>_r<版本号>
```