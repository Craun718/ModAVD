# 在 Linux 上从源码构建 ModAVD

这是 Linux x86_64 构建的流程。基于与 Windows 版（mas30）完全相同的源码
revision 和补丁，只换预编译工具链为 Linux 版本。

## 前置条件

- 64 位 Linux（Ubuntu 22.04 / 24.04 或 Debian 12 均可）。
- 已安装：Python 3.12+、Git、repo 工具、`git-lfs`。
- 磁盘空间：源码加构建中间件约 40 GB。
- `/dev/kvm` 可访问（用户加入 `kvm` 组，或者有 udev 规则）。

## 环境准备

```sh
sudo apt-get install -y git build-essential python3 python3-pip curl unzip xz-utils
mkdir -p ~/.local/bin
curl -sSL https://storage.googleapis.com/git-repo-downloads/repo -o ~/.local/bin/repo
chmod +x ~/.local/bin/repo
export PATH="$HOME/.local/bin:$PATH"
```

## 获取源码

Linux 清单基于 `manifest-aosp-base.xml`（全部是 AOSP 公开提交），
repo sync 之后再回放补丁得到目标源码。

```sh
git clone https://github.com/ModAVD/ModAVD.git
cd ModAVD
modavd="$(pwd)"

mkdir -p "$HOME/modavd-src"
cd "$HOME/modavd-src"

repo init -u https://android.googlesource.com/platform/manifest -b emu-main-dev --depth=1
cp "$modavd/manifests/manifest-aosp-base.xml" .repo/manifests/
repo init -u https://android.googlesource.com/platform/manifest -b emu-main-dev -m manifest-aosp-base.xml --depth=1
repo sync -c --no-clone-bundle -j4
```

## 回放补丁

按 `patches/BASE.md` 的顺序，用 `git am --keep-cr` 逐个仓库回放：

```sh
declare -A series=(
  ["external/qemu"]="qemu/fixq30"
  ["hardware/google/gfxstream"]="gfxstream/fixq28"
  ["external/crashpad"]="crashpad/module-version22"
)
for repo_path in external/qemu hardware/google/gfxstream external/crashpad; do
  patch_dir="${series[$repo_path]}"
  git -C "$repo_path" switch -c modavd-mas30
  patches=($(cd "$modavd/patches/$patch_dir" && ls *.patch | sort))
  patch_paths=()
  for p in "${patches[@]}"; do patch_paths+=("$modavd/patches/$patch_dir/$p"); done
  git -C "$repo_path" am --keep-cr "${patch_paths[@]}"
done
```

回放后，`git -C external/qemu rev-parse HEAD^{tree}` 应为
`b02675308b3373b734ca980a1492e0efe24c4970`（与 Windows 版相同）。

## 构建

```sh
export CMAKE_BUILD_PARALLEL_LEVEL=$(nproc)
out="$HOME/modavd-src/objs"
dist="$HOME/modavd-src/dist"
cd external/qemu
python3 android/build/python/cmake.py \
  --target=linux \
  --out "$out" --dist "$dist" \
  --task-disable clean --task-disable removeleftover --task-disable prebuilts \
  --task-disable ctest --task-disable emugentest --task-disable genentriestest \
  --task-disable coveragereport --task-disable packagesamples \
  --task-disable zipintegrationtests --task-disable integrationtest
```

构建产物在 `$out/distribution/emulator/`。

## 补丁的 Linux 适配说明

所有补丁直接修改源码文件，在 Linux 上 repo sync 后源码树相同，因此
`git am` 全部适用（包括 WHPX 补丁——它们修改的 `whpx-all.c` 在 Linux 上
编译时不参与链接，但源码文件存在，patch 可以干净地应用）。

构建系统会根据 `--target=linux` 选择 KVM 加速后端，不编译 WHPX 相关代码。

| 补丁类别 | Linux 上的状态 |
|---|---|
| WHPX（TSC、APIC、挂起恢复） | 不参与编译，无影响 |
| Windows 构建（VS、AUTOMOC、DISM） | 不参与编译，无影响 |
| Windows 运行时（DPI、os-win32） | 不参与编译，无影响 |
| Windows 网络（WSAPoll） | 不参与编译，Linux 用 poll() 正常行为 |
| NTFS / 文件系统优化 | 不参与编译或无意义，Linux 文件系统无此问题 |
| Windows 共享内存（MMAP 截图） | 需要验证——构建可能在链接时报缺少 Win32 API |
| slirp 网络 | 通用代码，参与编译 |
| gfxstream 全部 | 通用代码，参与编译 |
| 媒体解码 | 通用代码，参与编译 |
| 隐私 / 日志 / UI / 图标 | 通用代码，参与编译 |
| Crashpad Windows 补丁 | `util/win/` 目录在 Linux 上不参与编译 |

共享内存截图补丁（0005/0014）如果链接失败，需要在 Linux 上改用
`memfd_create` + `shm_open` 实现，这是预计的适配点。

