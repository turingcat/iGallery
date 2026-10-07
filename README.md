# iGallery

将 Immich 照片库变成树莓派数字相框：后端缓存照片，Chromium 全屏轮播，HDMI 输出到 BOE 画屏或普通显示器。NAS 短时不可用时继续播放本地照片，API Key 不进入浏览器。

## 首版功能

- 随机照片或指定单个相册；跳过视频。
- 默认缓存 100 张 preview 图片，每 10 分钟刷新，每 30 秒切换。
- 持久缓存、原子清单更新、服务重启恢复；换批下载失败保留旧照片。
- 提前加载、淡入切换、完整画面显示，不强制裁剪；兼容桌面与移动浏览器。
- systemd 后端与 Chromium kiosk 部署模板。
- 照片右下角显示拍摄日期，文字颜色自适应背景，日期随照片离线缓存；Chromium kiosk 禁用翻译提示。

不包含 MT Photos、人物/地点筛选、视频、管理后台、Docker。公开仓库尚未选择开源许可证。

## 运行

需要 Python 3.11+。在树莓派推荐 Raspberry Pi OS 64-bit 桌面版，以及可访问 Immich 的网络。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

在私密文件中按 `.env.example` 配置环境变量；不要提交真实配置。生产部署使用 systemd 的 `/etc/igallery.env`，详见 `docs/deployment.md`。开发时可使用下面的方法读取你自己创建的可信配置文件（权限 0600），不要把密钥写在命令行：

```bash
set -a
. /absolute/path/to/private-igallery.env
set +a
.venv/bin/python -m igallery
```

浏览器打开 `http://127.0.0.1:8080`。默认只监听回环地址，不向局域网开放家庭照片。

## 配置

| 环境变量 | 默认值 / 说明 |
| --- | --- |
| `IMMICH_URL` | 必填；服务器根地址，允许尾随 `/api` 或部署子路径 |
| `IMMICH_API_KEY` | 必填；只在后端使用 |
| `IMMICH_ALBUM_ID` | 留空随机播放；设置合法 UUID 时读取指定相册 |
| `IGALLERY_CACHE_DIR` | `~/.cache/igallery`；systemd 固定 `/var/lib/igallery` |
| `IGALLERY_CACHE_COUNT` | `100`；1–1000 |
| `IGALLERY_INTERVAL_SECONDS` | `30`；正整数 |
| `IGALLERY_REFRESH_SECONDS` | `600`；正整数 |

缩略图固定 `preview`，本地 JPEG 最长边不超过 1920，quality 85。应用直接连接配置地址，不使用环境中的代理设置；使用 Tailscale 地址时需要操作系统已有可达路由。

Immich 官方主线 OpenAPI 的必要权限：随机搜索 `asset.read`、preview `asset.view`；相册模式另需 `album.read`。不同安装版本可能存在差异，应按实际版本的权限选项核对，不使用管理员 Key 规避权限错误。

## 接口

| 接口 | 用途 |
| --- | --- |
| `GET /` | 幻灯片 |
| `GET /api/photos` | 本地照片清单及切换间隔 |
| `GET /api/photo/{id}` | 清单允许的缓存照片 |
| `GET /health` | 服务存活、缓存数、最近刷新结果 |

健康检查的 `status: ok` 只表示本地服务存活，不表示 NAS 可达。首次没有缓存且网络不可用时显示等待提示。

## 开发验证

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
npm ci
npm test
npx playwright install chromium
npm run test:browser
bash -n deploy/kiosk.sh
```

Node 只用于开发测试，部署不需要 Node 或前端构建。测试使用生成图片和假 API，不依赖真实 Immich 或凭据。

## 安全与部署

部署步骤、labwc/LXDE 自启动和故障排查见 `docs/deployment.md`。API Key、密码、环境文件、缓存照片均不得进入 Git；若密钥曾通过聊天或截图传递，部署后建议轮换。内网 HTTP 不提供传输加密，应仅使用可信局域网或已加密的 Tailscale 网络。

参考：[Immich API](https://api.immich.app/endpoints/search/searchRandom)、[Immich 官方 OpenAPI](https://github.com/immich-app/immich/blob/main/open-api/immich-openapi-specs.json)、[Raspberry Pi kiosk 教程](https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/)。
