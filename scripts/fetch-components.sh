#!/usr/bin/env bash
# ModAVD Linux: download adb and Android system image from Google.
# Replaces the Windows "补全组件.bat" on Linux.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SDK_DIR="$SCRIPT_DIR/sdk"
DL_DIR="$SCRIPT_DIR/downloads"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/fetch-components.log"

PLATFORM_TOOLS_URL_NAME="platform-tools_r37.0.1-linux.zip"
PLATFORM_TOOLS_SHA1="477254aa5f903c15cf51001717bdf347fb6b53e0"
PLATFORM_TOOLS_EXPECTED_BYTES=8044989

SYSIMG_URL_NAME="x86_64-34_r14.zip"
SYSIMG_SHA1="e0f6c9a0691aa27bd597d0deb1bcfdc943ac8ca7"

LICENSE_ID="android-sdk-license"
LICENSE_TEXT_URL_PATH="android/repository/licenses/android-sdk-license.txt"

MIRRORS=(
  "https://googledownloads.cn"
  "https://dl.google.com"
)

mkdir -p "$SDK_DIR" "$DL_DIR" "$LOG_DIR"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
fail() { log "ERROR: $*" >&2; exit 1; }

find_downloader() {
  if command -v curl >/dev/null 2>&1; then
    echo "curl"
  elif command -v wget >/dev/null 2>&1; then
    echo "wget"
  else
    fail "需要 curl 或 wget 下载组件"
  fi
}

download() {
  local url="$1" dest="$2"
  local dl
  dl="$(find_downloader)"
  log "下载: $url"
  if [ "$dl" = "curl" ]; then
    curl -fSL --retry 3 --connect-timeout 15 -o "$dest" "$url" 2>&1 | tee -a "$LOG_FILE"
  else
    wget -q --tries=3 --timeout=15 -O "$dest" "$url" 2>&1 | tee -a "$LOG_FILE"
  fi
}

sha1_of() {
  if command -v sha1sum >/dev/null 2>&1; then
    sha1sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 1 "$1" | cut -d' ' -f1
  else
    fail "需要 sha1sum 或 shasum 校验文件"
  fi
}

check_ascii_path() {
  case "$SCRIPT_DIR" in
    *[![:print:]]*|*[!A-Za-z0-9_./-]*)
      fail "路径含有非英文或非常规字符: $SCRIPT_DIR
请把整个文件夹挪到只含英文和数字的路径下再运行。"
      ;;
  esac
}

check_space() {
  local need_mb="$1"
  local avail_kb
  avail_kb=$(df -Pk "$SCRIPT_DIR" | awk 'NR==2 {print $4}')
  if [ "$avail_kb" -lt "$((need_mb * 1024))" ]; then
    fail "磁盘空间不够: 需要 ${need_mb} MB，可用 $((avail_kb / 1024)) MB"
  fi
}

fetch_license() {
  local license_file="$DL_DIR/${LICENSE_ID}.txt"
  if [ -f "$license_file" ]; then
    log "许可协议已下载，跳过获取"
    cat "$license_file"
    return 0
  fi
  local text=""
  for mirror in "${MIRRORS[@]}"; do
    local url="$mirror/$LICENSE_TEXT_URL_PATH"
    log "获取许可协议: $url"
    if command -v curl >/dev/null 2>&1; then
      text=$(curl -fsSL --connect-timeout 10 "$url" 2>/dev/null) && [ -n "$text" ] && break
    else
      text=$(wget -qO- --timeout=10 "$url" 2>/dev/null) && [ -n "$text" ] && break
    fi
    text=""
  done
  [ -n "$text" ] || fail "取不到许可协议全文；检查网络后重试"
  printf '%s\n' "$text" > "$license_file"
  cat "$license_file"
}

ask_agree() {
  printf '\n输入 y 同意上述协议并继续下载，其他内容或直接回车退出: '
  read -r answer
  [ "$answer" = "y" ] || { log "未同意，退出"; exit 0; }
  echo "y" >> "$LOG_FILE"
}

try_download_with_mirrors() {
  local repo_path="$1" dest="$2"
  for mirror in "${MIRRORS[@]}"; do
    local url="$mirror/android/repository/$repo_path"
    if download "$url" "$dest"; then
      return 0
    fi
    log "下载失败，换下一个镜像"
    rm -f "$dest"
  done
  return 1
}

install_platform_tools() {
  local target="$SDK_DIR/platform-tools"
  if [ -x "$target/adb" ]; then
    log "adb 已安装，跳过"
    return 0
  fi
  check_space 300
  local zip_file="$DL_DIR/$PLATFORM_TOOLS_URL_NAME"
  if [ ! -f "$zip_file" ] || [ "$(sha1_of "$zip_file" 2>/dev/null)" != "$PLATFORM_TOOLS_SHA1" ]; then
    try_download_with_mirrors "$PLATFORM_TOOLS_URL_NAME" "$zip_file" \
      || fail "平台工具下载失败；所有镜像都不通"
  fi
  local actual_sha1
  actual_sha1=$(sha1_of "$zip_file")
  [ "$actual_sha1" = "$PLATFORM_TOOLS_SHA1" ] \
    || fail "平台工具校验不对: 期望 $PLATFORM_TOOLS_SHA1，实际 $actual_sha1"
  log "校验通过，解压到 $target"
  unzip -qo "$zip_file" -d "$SDK_DIR"
  chmod +x "$target/adb"
  rm -f "$zip_file"
  log "adb 安装完成"
}

install_system_image() {
  local target="$SDK_DIR/system-images/android-34/google_apis/x86_64"
  if [ -f "$target/system.img" ]; then
    log "系统镜像已安装，跳过"
    return 0
  fi
  check_space 6000
  local zip_file="$DL_DIR/$SYSIMG_URL_NAME"
  if [ ! -f "$zip_file" ] || [ "$(sha1_of "$zip_file" 2>/dev/null)" != "$SYSIMG_SHA1" ]; then
    try_download_with_mirrors "$SYSIMG_URL_NAME" "$zip_file" \
      || fail "系统镜像下载失败；所有镜像都不通"
  fi
  local actual_sha1
  actual_sha1=$(sha1_of "$zip_file")
  [ "$actual_sha1" = "$SYSIMG_SHA1" ] \
    || fail "系统镜像校验不对: 期望 $SYSIMG_SHA1，实际 $actual_sha1"
  log "校验通过，解压到 $target"
  mkdir -p "$(dirname "$target")"
  unzip -qo "$zip_file" -d "$(dirname "$target")"
  rm -f "$zip_file"
  log "系统镜像安装完成"
}

main() {
  check_ascii_path
  log "ModAVD 组件下载脚本启动: $SCRIPT_DIR"
  fetch_license
  ask_agree
  install_platform_tools
  install_system_image
  log "完成，可以启动模拟器了。"
}

main "$@"
