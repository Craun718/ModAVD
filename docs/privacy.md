# 隐私

这里说的「模拟器」指 Release 包里 `sdk\emulator\` 下的程序，运行在你的 Windows 上。安卓系统和里面的应用另说，见后文。

## 模拟器自己不联网

官方 Android Emulator 会在后台访问 Google 的服务器。ModAVD 把这些都去掉了：

| 官方版的行为 | ModAVD |
|---|---|
| 带 `-metrics-collection` 时，把使用统计（含安装 ID、系统版本、本次会话的使用事件）上传到 `play.googleapis.com` | 不上传。`-metrics-collection` 按 `-no-metrics` 处理 |
| 崩溃时按设置上传崩溃转储到 `clients2.google.com`，带窗口时可能弹窗询问 | 不上传，不询问，转储只留在本机 |
| 每次开机（同一版本 4 小时一次）带安装 ID、系统和版本访问 `dl.google.com` 检查更新 | 不检查。开机日志里有一行 `Update check skipped: this build never checks for updates; upgrades come from whoever distributed it.` |
| 每 24 小时从 `dl.google.com` 下载一次特性开关 | 不下载，用本地缓存或包里自带的那一份。开机日志里有一行 `Feature patterns are not downloaded: this build never fetches them and keeps using the cached or shipped ones.` |

我们在测试时同时用了三种办法核对：模拟器的 libcurl 详细日志（电脑这边所有 HTTP 请求都会记下）、每秒一轮的进程连接表、Windows 的 DNS 缓存。开机、压测、正常关机、故意让它崩溃，`emulator.exe`、`qemu-system` 自己的代码和 `crashpad_handler.exe` 都没有往外连。对应的改动见 `patches/qemu/fixq30/` 里标题以 `MAS local` 开头、讲崩溃报告、使用统计、更新检查和特性开关的那几个补丁（0036、0038、0039、0045–0049）。

**例外**：

- 带窗口运行时，如果打开扩展控制窗口里的「位置」页，它会从 `dl.google.com` 取地图密钥并加载 Google 地图。不打开这个页面就不会访问；无头运行时没有这个页面。默认的精简工具栏上没有打开扩展控制的按钮。
- 虚拟场景相机的街景功能要设环境变量才会打开，默认关闭；Release 包也没有带虚拟场景的资源文件。
- 扩展控制里帮助、反馈等页面上的链接，要你点了才会用浏览器打开。

`-metrics-to-file`、`-metrics-to-console` 这两个参数仍然有效，只在你显式给出时把统计写到本地文件或控制台。

## 安卓系统和应用照常联网

安卓系统、游戏，以及 Google APIs 系统镜像里自带的 Google Play 服务，都通过模拟器的虚拟网络照常上网。这是它们自己的流量，和在手机上一样，模拟器不拦也不改。

## 崩溃转储只留在本机

- 位置：`%TEMP%\AndroidEmulator\emu-crash-37.2.10-mas.db\`。可以用环境变量 `ANDROID_EMU_CRASH_REPORTING_DATABASE` 改到别处。
- 保留最新 5 份，更旧的开机时自动删掉。份数可以用 `ANDROID_EMU_CRASH_REPORTS_TO_KEEP` 改（1 到 100）。
- 内容：模拟器进程的线程栈、少量内存片段和本机路径（路径里有 Windows 用户名）。不包含安卓系统的完整内存，也不会有意收集账号密码。
- 不想留：开机参数加 `-crash-report-mode disabled` 会完全关掉崩溃记录；已有的直接删掉上面那个文件夹即可。

## 两个脚本

- **补全组件.bat**：只在你运行它时联网，依次访问 googledownloads.cn、mirrors.cloud.tencent.com、dl.google.com，下载许可协议清单、adb 和系统镜像。请求里只有普通的下载信息（用户代理是 `ModAVD-fetch-components/1.0`），不带任何标识。过程记在文件夹里的 `logs\fetch-components.log`。
- **收集问题信息.bat**：只在本机读文件、打包，不联网，也不上传。它会读模拟器和 AUTO-MAS 的日志、崩溃转储，开着的实例还会截一张图；不碰实例的磁盘镜像，也不碰 AUTO-MAS 存账号密码的 `config`、`data` 文件夹。生成的 zip 要不要发由你决定；崩溃转储不要公开上传，要发就发邮件，见 [feedback.md](feedback.md)。

## 本项目不收集任何数据

ModAVD 没有服务器，也没有任何统计。我们能看到的，只有你自己在 Issues 里贴出来的内容和你发到反馈邮箱的问题包。
