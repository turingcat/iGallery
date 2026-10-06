# 树莓派部署

## 1. 预检

通过 SSH 连接设备，保留主机密钥校验；未知指纹先核实，冲突时停止。密码不要放在脚本、命令参数或 Git 中。

```bash
uname -m
cat /etc/os-release
python3 --version
command -v chromium chromium-browser
echo "$XDG_SESSION_TYPE"
ls ~/.config/labwc ~/.config/lxsession /etc/xdg/labwc 2>/dev/null
df -h /
```

需要 Python 3.11+、图形桌面和 Chromium。纯 Lite 系统不能仅靠后端服务显示画面。`XDG_SESSION_TYPE` 在 SSH 中可能为空，应在真实桌面会话核对。

用你自己的地址测试 `GET /api/server/ping`。Tailscale IP 不会在普通局域网自动可达：先在设备上建立已授权的 Tailscale 连接，或改用已有可达的局域网 Immich 地址。应用不会安装 Tailscale、自动登录或修改路由。

## 2. 应用安装

先确认 `/opt/igallery` 和 `igallery.service` 没有已有安装；升级时备份环境文件、unit、缓存清单及自启动配置。

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip chromium curl git
sudo install -d -o pi -g pi /opt/igallery
git clone https://github.com/turingcat/iGallery.git /opt/igallery
cd /opt/igallery
python3 -m venv .venv
.venv/bin/python -m pip install .
sudo install -m 600 -o root -g root .env.example /etc/igallery.env
sudoedit /etc/igallery.env
```

在编辑器中填入真实地址与只读 API Key，不在 shell 命令中输入 Key。systemd 环境文件不是 shell 脚本，不使用 `export`；值有空格时使用双引号。实际用户不是 `pi` 时先修改 unit 的 User 和目录权限。

```bash
sudo install -m 644 deploy/igallery.service /etc/systemd/system/igallery.service
sudo systemd-analyze verify /etc/systemd/system/igallery.service
sudo systemctl daemon-reload
sudo systemctl enable --now igallery
curl --noproxy '*' -fsS http://127.0.0.1:8080/health
```

修改配置后执行 `sudo systemctl restart igallery`。缓存持久保存在 `/var/lib/igallery`，轮播不需要 NAS 每次切图都在线。

## 3. Chromium 自动全屏

必须在登录后的桌面会话中启动，不能用普通 systemd 系统服务直接启动 GUI。脚本使用专用 Chromium profile，不影响用户普通浏览器。

labwc 桌面：如果用户没有 `~/.config/labwc/autostart`，先复制 `/etc/xdg/labwc/autostart`（存在时），以保留面板等默认启动项；已有文件先备份，不能覆盖。

```bash
mkdir -p ~/.config/labwc
if [ ! -f ~/.config/labwc/autostart ] && [ -f /etc/xdg/labwc/autostart ]; then
    cp /etc/xdg/labwc/autostart ~/.config/labwc/autostart
fi
cp ~/.config/labwc/autostart ~/.config/labwc/autostart.igallery-backup
grep -qF '/opt/igallery/deploy/kiosk.sh' ~/.config/labwc/autostart || \
    printf '\nbash /opt/igallery/deploy/kiosk.sh &\n' >> ~/.config/labwc/autostart
```

如果用户和系统 autostart 都不存在，先 `touch ~/.config/labwc/autostart` 再备份/追加。LXDE/X11 桌面则在实际使用的 `~/.config/lxsession/<会话名>/autostart` 备份后追加 `@bash /opt/igallery/deploy/kiosk.sh`，不要误用 labwc 配置。

可先从桌面终端运行 `bash /opt/igallery/deploy/kiosk.sh` 验证。无人值守启动还需要桌面自动登录；请在设备实际设置界面配置，并确认安全影响。

## 4. 显示与验收

在桌面显示设置中选择 HDMI、1920×1080、100% 缩放。方向按画屏实际摆放确认，不强制旋转。关闭屏幕空闲熄屏与睡眠应按实际 labwc/X11 环境操作；不要直接套用另一桌面的 `xset` 命令。

- `/health` 的缓存数大于 0，本机 `/api/photos` 可列出图片。
- Chromium 完整显示照片，按间隔切换；竖图允许留黑边。
- NAS 故障时保留原照片；后端重启仍能播放缓存。
- 确认服务 enabled、桌面自启动与显示设置，再在允许的维护窗口整机重启。
- BOE HDMI 输入源、实际画面、长期不熄屏与重启全屏效果需要现场确认；远程服务健康不等于物理屏幕已经正常。

## 5. 故障排查

```bash
systemctl status igallery --no-pager
journalctl -u igallery --since '10 minutes ago' --no-pager
curl --noproxy '*' -fsS http://127.0.0.1:8080/health
```

`source_status` 常见于鉴权或服务器错误；检查实际 Immich 版本和 Key 权限。`source_request` 检查路由与 NAS 服务；`cache_photo_failed` 检查内容与磁盘。应用不记录响应原文或 Key。遇到等待页面先查看缓存数量，不要为了排障公开环境文件或照片。

删除服务时先 `sudo systemctl disable --now igallery`，移除自启动中自己追加的一行，保留其他条目；是否删除缓存与配置由设备所有者决定。

## 当前设备预检记录

- 已确认 ARM64、Debian 13、Python 3.13.5、Chromium、labwc 配置目录。
- 指定 Immich 地址从开发电脑可达；树莓派访问超时，未发现 tailscale 命令。
- 尚未修改网络、桌面或显示配置；生产照片联调需先解决网络前置条件。
- 开发电脑真实联调已确认 Immich v3.2.4：获取并缓存 3 张预览图成功，重新载入缓存恢复 3 张，模拟上游故障仍保留全部 3 张。
- 此记录不代表树莓派或 BOE 实际显示已验收。
