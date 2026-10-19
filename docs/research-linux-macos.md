# 研究：适配 Linux 和 macOS 的可行性

当前版本（37.2.10-mas30）是 Windows 专用构建，核心依赖 WHPX 做硬件加速。
本文分析把同一套补丁适配到 Linux 和 macOS 的工作量。

## 结论

**可行，但分阶段。** 上游 AOSP Android Emulator（`platform/external/qemu`）本来就支持
Linux（KVM）和 macOS（Hypervisor.framework）构建，构建系统接受 `--target=linux` 和
`--target=darwin`。gfxstream 也声明支持 Linux 和 macOS 作为宿主平台。大部分 ModAVD
补丁写在跨平台代码里（gfxstream、slirp、Android 层），理论上能直接使用。

主要工作在于：
1. 构建清单和预编译库要换成 Linux/macOS 版本；
2. WHPX 专属补丁不需要移植（Linux 用 KVM，macOS 用 HVF，QEMU 对两者有原生支持）；
3. Windows 专属基础设施（.bat 脚本、NTFS 优化、DISM 检查）需要替代实现；
4. AUTO-MAS 集成和发行方式要重做。

## 上游跨平台支持

AOSP `external/qemu` 的 `android/docs/` 下有 `LINUX-DEV.md` 和 `DARWIN-DEV.md`，
构建目标枚举为 `<windows|linux|darwin|mingw>`。Linux 构建用 KVM 加速，macOS 用
Hypervisor.framework（HVF）。这两个后端在 QEMU 里都有完整实现，WHPX 的 TSC 同步、
local APIC、挂起恢复等补丁在 KVM 和 HVF 上要么不是问题、要么已有不同实现。

gfxstream（`platform/hardware/google/gfxstream`）的 README 明确列出支持
Windows、Linux、macOS 作为宿主。Linux 上走 Vulkan ICD（NVIDIA 或 Mesa），
macOS 上走 MoltenVK。

## 补丁平台耦合分析

三个补丁仓库共 78 个提交。按平台依赖度分类：

### 跨平台（预计直接适用，约 50 个）

| 领域 | 补丁 | 说明 |
|------|------|------|
| gfxstream 通用修复 | 0001–0003, 0005–0008, 0013, 0015, 0016, 0019–0022 | Vulkan/GL 帧缓冲、描述符模板、YUV 转换等，不依赖平台 API |
| gfxstream 诊断日志 | 0009, 0010, 0021, 0022（MAS local） | 同上 |
| gfxstream MAS 内存 | 0011, 0012（WC 内存类型） | 实验性，需要验证在 Linux/macOS 显卡上的行为 |
| slirp 网络 | 0018, 0020, 0025 | TCP 缓冲区、ICMP 限制、TCP 保活，QEMU 通用 slirp 代码 |
| 媒体解码 | 0042, 0043, 0050, 0051, 0052 | CUDA/VPX/H264/HEVC 解码器纹理管理，跨平台 |
| 隐私 / 零外连 | 0045–0049（MAS local） | 崩溃上传、使用统计、更新检查，全在 Android 层 |
| 日志 | 0037, 0041, 0044 | stdio 行为修正，代码本身跨平台 |
| UI / 工具栏 | 0054 | Qt 界面，跨平台 |
| 图标 | 0055 | 资源替换，跨平台 |
| vCPU 上限 | 0026 | `main.cpp` 层，不绑定平台 |

### 仅 Windows（不需要移植，约 20 个）

| 领域 | 补丁 | 原因 |
|------|------|------|
| WHPX TSC/APIC | 0001, 0010, 0011, 0017, 0021, 0022, 0023, 0024, 0028, 0029, 0030 | `whpx-all.c`、`whp-dispatch.h`，Linux KVM / macOS HVF 有自己的寄存器管理 |
| WHPX 挂起恢复 | 0017 | 同上 |
| Windows 构建 | 0002（VS 2022）, 0003（Windows AUTOMOC）, 0004（DISM API） | 仅适用 MSVC / Windows SDK |
| Windows 运行时 | 0031（DPI 重绘）, 0040（os-win32 stderr 缓冲） | 平台特定 |
| Windows 网络 | 0016（WSAPoll POLLHUP/POLLERR） | Windows poll 实现差异，Linux/macOS 不存在 |
| NTFS / 文件系统 | 0035（虚拟气球回写在 Windows），0053（数据盘不预留空间） | NTFS / ReFS 特定行为 |
| 共享内存 | 0005, 0014（MMAP 截图句柄） | Windows 命名共享内存，需要用 POSIX shm 重做 |
| Crashpad Windows | crashpad/0001 | `util/win/module_version.cc`，Linux/macOS 有各自的 Crashpad 后端 |

### 需要平台适配（约 8 个）

| 领域 | 补丁 | 适配方向 |
|------|------|---------|
| gfxstream WGL | 0014, 0017, 0018 | 改的是 `egl_os_api_wgl.cpp`（Windows WGL），Linux 对应 EGL/X11 或 EGL/Wayland |
| Crashpad 本地存储 | 0036, 0038, 0039 | 改的是跨平台崩溃上传逻辑，但路径和数据库格式可能因平台不同需验证 |
| 共享内存 | 0005, 0014 的替代 | 用 POSIX `shm_open` / `memfd_create` 重写截图共享内存 |

## 构建适配

### 清单和预编译库

当前 `manifest-mas30.xml` 只含 `windows-x86` 预编译库（`groups="notdefault,platform-windows"`）。
上游 `emu-main-dev` 分支同时维护 `linux-x86`、`darwin-x86`、`darwin-aarch64` 预编译库
（`prebuilts/android-emulator-build/{qt,mesa,qemu-android-deps,...}` 下按平台分子目录）。

适配方法：以同一套源码 revision 为基础，把 `platform-windows` 组的项目替换为对应平台的
组（`platform-linux` / `platform-darwin`），预编译库 revision 从上游同一 emu-main-dev 分支取。
需要确认的是这些预编译库在 mas30 对应时间点的 revision 是否仍然可用。

### 构建命令

```sh
# Linux
cd external/qemu
python android/build/python/cmake.py --target=linux ...

# macOS (Intel)
python android/build/python/cmake.py --target=darwin ...

# macOS (Apple Silicon)
python android/build/python/cmake.py --target=darwin_aarch64 ...
```

构建脚本和 CI 需要新增 Linux/macOS 流水线。

## 运行时平台差异

### Linux

- 硬件加速：KVM。要求 `/dev/kvm` 可访问（用户在 `kvm` 组或 udev 规则）。
  KVM 是 QEMU 最成熟的后端，WHPX 补丁解决的问题（TSC 漂移、挂起后时钟、
  local APIC 模拟）在 KVM 上要么不存在、要么由内核模块处理。
- 图形：gfxstream 走 Vulkan ICD。NVIDIA 专有驱动和 Mesa（AMD/Intel）的行为
  差异较大，需要在两类驱动上分别测试。ModAVD 修的几个 Vulkan bug
  （NVIDIA 2–5% 黑帧、描述符模板、ASTC 转 BC3）可能只影响 NVIDIA，
  但需要在 Linux NVIDIA 上复现确认。
- 文件系统：ext4 / xfs / btrfs 都支持 sparse file 和 fallocate，
  不存在 NTFS 预分配问题，0053 补丁可能不需要。
- 桌面：Qt 支持 X11 和 Wayland。无头运行不需要桌面。
- 发行：tar.gz / AppImage / DEB / RPM 均可，脚本用 POSIX shell。

### macOS

- 硬件加速：HVF（Hypervisor.framework）。x86_64 Mac 上直接可用。
  Apple Silicon（M 系列）上运行 x86_64 客体需要 Rosetta 2 或 ARM64 系统镜像，
  后者意味着换一组完全不同的 Android 系统镜像（android-arm64-v8a），
  是一个独立的大工程。
- 图形：gfxstream 走 MoltenVK（Vulkan-on-Metal）。模拟器 UI 走 Qt/Cocoa。
  Vulkan 的功能覆盖和稳定性取决于 MoltenVK 的成熟度，某些游戏
  （依赖 Vulkan 特性的）可能在 macOS 上行为不同。
- 文件系统：APFS，支持 sparse file。
- 发行：.app bundle 或 tar.gz，需要处理代码签名和公证。

## 基础设施

| Windows 现状 | Linux/macOS 替代 |
|---|---|
| 补全组件.bat（PowerShell 脚本） | bash / zsh 脚本 |
| 收集问题信息.bat | bash / zsh 脚本 |
| NTFS 路径检查（只允许英数） | POSIX 路径无此限制，但仍建议无空格 |
| AUTO-MAS Windows 集成 | 需要等 AUTO-MAS 侧支持或提供独立 CLI |
| Windows 功能（WHPX） | Linux: `kvm` 模块；macOS: Hypervisor.framework 内置 |

## 工作量估计

| 目标 | 难度 | 预估 |
|------|------|------|
| Linux x86_64（KVM + NVIDIA/Mesa） | 中 | 2–4 周（验证补丁适用、构建清单、写脚本、跑通游戏） |
| macOS Intel x86_64（HVF + MoltenVK） | 中偏高 | 3–6 周（HVF 比 KVM 少有人用，MoltenVK 兼容性需要测试） |
| macOS Apple Silicon ARM64 | 高 | 2–3 月+（需要 ARM64 系统镜像，QEMU 架构改动大） |

建议先做 Linux x86_64，验证跨平台补丁的适用性后再做 macOS。

