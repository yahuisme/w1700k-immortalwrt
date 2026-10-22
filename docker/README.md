# ARM64 构建环境

工作流使用此目录构建 Debian ARM64 镜像，并按实际镜像 ID 启动容器。镜像不预装固件源码、工具链或编译缓存。

- Debian 基础镜像摘要固定，apt 软件包正常接收官方更新。
- Go 引导工具来自官方 ARM64 归档，校验 SHA256 后安装到 `/usr/lib/go`；最终 Go 编译器仍由 feed 构建。
- 缓存使用 pigz 压缩；工具链兼容性由配方、实际软件包清单和构建输入共同判定。
- 不提供主机 LLVM；最终配置选择 `CONFIG_USE_LLVM_HOST=y` 时停止构建，避免缺工具后继续执行。

在空源码容器中运行以下命令可检查依赖、Go、Git 和归档操作，不执行编译：

```sh
bash /builder-context/smoke.sh
```

缓存输入与恢复约定见 [`tests/CACHE_KEY_REVIEW.md`](../tests/CACHE_KEY_REVIEW.md)。
