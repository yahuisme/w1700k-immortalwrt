# AI 协力构建的 Quantum Fiber W1700K ImmortalWrt 固件

适用于 **Quantum Fiber W1700K** 路由器的定制 ImmortalWrt 固件构建项目。

本项目基于 [w1700k/builds](https://github.com/w1700k/builds) 的构建框架，源码基线为 [ImmortalWrt 官方 snapshot（master）](https://github.com/immortalwrt/immortalwrt)，内置应用、配置与汉化与 [w1700k-openwrt](https://github.com/yahuisme/w1700k-openwrt) 项目保持一致（值守式系统升级除外）。

> ⚠️ **仅适用于 Quantum Fiber W1700K，请勿刷入其他型号设备。**

---

## ✨ 主要特性

- 📝 内置专属应用已添加中文汉化
- 🎨 内置 Aurora LuCI 主题为默认主题
- 🕐 系统时区：香港（UTC+8）
- 📡 默认开启 2.4 GHz / 5 GHz Wi-Fi
- 📡 默认不开启 6 GHz Wi-Fi
- 🌡️ LuCI 首页增加设备温度及风扇转速显示
- 🔄 每日自动构建最新固件
- 📦 提供 `ubi2` 常规版本

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
```

---

## 说明

- 与 w1700k-openwrt 的差异：源码基线为 ImmortalWrt 官方 snapshot（master），其余内置应用、默认配置与汉化一致。