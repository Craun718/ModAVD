# 在 Linux 上安装 ModAVD

## 开始前确认

- Linux x86_64（Ubuntu 22.04+、Debian 12+、Fedora 39+ 等）。
- CPU 支持 KVM，且 `/dev/kvm` 可访问。
  检查：`ls -l /dev/kvm` 存在且当前用户有读写权限（通常加入 `kvm` 组即可）。
- 显卡支持 Vulkan。NVIDIA 需要 NVIDIA 专有驱动（nvidia-driver 535+）；
  AMD / Intel 用 Mesa（RADV / ANV），需 23.0+。
- 磁盘：安装组件要约 6.5 GB；每台实例首次开机要 10 GB 以上可用。

## 安装步骤

### 1. 下载并解压

从 Releases 下载 `ModAVD-<版本>-linux.tar.gz`，解压到纯英文路径：

```sh
tar xzf ModAVD-*.tar.gz
cd ModAVD-*/
```

### 2. 补全组件

```sh
chmod +x fetch-components.sh
./fetch-components.sh
```

脚本会先显示 Google《Android SDK 许可协议》，输入 `y` 同意后下载：
- 平台工具（adb）37.0.1（Linux 版），约 8 MB；
- 系统镜像 Android 14 (API 34) Google APIs x86_64 r14，约 1.5 GB。

下载顺序：googledownloads.cn → 腾讯云镜像 → dl.google.com。
已装好的组件会跳过，重复运行无副作用。

### 3. 确认 KVM

```sh
kvm-ok
```

如果没有 `kvm-ok`，用这个代替：
```sh
grep -cE 'vmx|svm' /proc/cpuinfo
ls -l /dev/kvm
```

`/proc/cpuinfo` 里有 `vmx`（Intel）或 `svm`（AMD），且 `/dev/kvm` 存在即可。
当前用户没有 `/dev/kvm` 权限时，加入 `kvm` 组后重新登录：
```sh
sudo usermod -aG kvm "$USER"
```

### 4. 启动

```sh
./sdk/emulator/emulator -avd <实例名>
```

无头（不显示窗口）：
```sh
./sdk/emulator/emulator -avd <实例名> -no-window
```

## 目录结构

| 路径 | 内容 |
|---|---|
| `sdk/emulator/` | 模拟器本体 |
| `sdk/platform-tools/` | adb |
| `sdk/system-images/` | Android 系统镜像 |
| `avd/` | 实例数据 |
| `fetch-components.sh` | 组件下载脚本 |
| `collect-diagnostics.sh` | 问题信息收集脚本 |

## 故障排查

| 现象 | 原因和解决 |
|---|---|
| `Failed to open /dev/kvm` | KVM 权限不够，见上节 |
| `KVM is required` | BIOS 里没开虚拟化（VT-x / AMD-V） |
| 启动后黑屏 / 花屏 | 显卡驱动问题。NVIDIA 需要专有驱动 + Vulkan ICD；Mesa 需要 23.0+ |
| Vulkan 验证层报错 | 设 `VK_LOADER_DEBUG=all` 查看详情；或设 `ANDROID_EMU_VK_CACHED_COHERENT=1` 尝试 |
| 路径有中文/空格启动失败 | 把整个文件夹挪到纯英文无空格路径下 |

