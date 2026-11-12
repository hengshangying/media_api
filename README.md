# media-api

影音播放器的片库后端：FastAPI 提供列表、详情、直链播放（支持 HTTP Range）和上传。

配套前端仓库：[media_player](https://github.com/hengshangying/media_player)

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 把 MEDIA_API_TOKEN 改成你自己的随机字符串
./start.sh
```

健康检查（无需鉴权）：

```bash
curl http://127.0.0.1:8787/health
```

业务接口需要请求头 `Authorization: Bearer <MEDIA_API_TOKEN>`。接口说明见 [docs/API_DRAFT.md](docs/API_DRAFT.md)。

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `MEDIA_API_TOKEN` | 静态 Bearer token | 请自行生成，不要提交到 Git |
| `MEDIA_ROOT` | 媒体与元数据目录 | `./media` |
| `MEDIA_API_HOST` | 监听地址 | `0.0.0.0` |
| `MEDIA_API_PORT` | 监听端口 | `8787` |
| `MEDIA_PUBLIC_BASE` | 返回给客户端的公开基址（封面、播放地址） | `http://127.0.0.1:8787` |

`MEDIA_ROOT` 会在启动时自动创建 `movies/`、`shows/`、`music/`、`uploads/`、`.meta/`。

## 反代建议

如用 Nginx 反代到本服务：

- 转发 `Authorization`、`Range`
- `proxy_buffering off`（避免视频流被整段缓冲）
- 不要给流请求额外加上 `Accept: application/json`
- 上传可设 `client_max_body_size 2g`，并加长 `proxy_read_timeout`

播放器应使用你的公开 baseUrl 自行拼接 `/api/v1/videos/{id}/stream` 等路径；或把该基址写入 `MEDIA_PUBLIC_BASE`。

## 入口

- 应用：`app.main:app`
- 启动：`./start.sh`（前台，依赖 `.env`）
- 停止：`./stop.sh`
