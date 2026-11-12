# 影音后端 API 草案 v0.1（临时约定）

服务名：media-api  
版本：v1  
协议：HTTPS/HTTP + JSON  
鉴权：`Authorization: Bearer <API_TOKEN>`（开发期静态 token；后续可换登录发 JWT）

## 环境

| 环境 | base URL | 说明 |
|------|----------|------|
| 本地开发 | `http://127.0.0.1:8787` | 复制 `.env.example` 为 `.env` 后启动 |
| 部署 | 以 `MEDIA_PUBLIC_BASE` 为准 | 反代或公网入口，不要把真实 token 提交到仓库 |

开发 token：写在本机 `.env` 的 `MEDIA_API_TOKEN`，不要提交 `.env`。

通用响应包装：
```json
{ "ok": true, "data": { }, "error": null }
```
失败：
```json
{ "ok": false, "data": null, "error": { "code": "NOT_FOUND", "message": "..." } }
```

---

## 1. 视频列表

`GET /api/v1/videos`

Query：
- `q` string 可选，搜索标题
- `type` string 可选：`movie` | `episode` | `music` | `all`（默认 all）
- `page` int 默认 1
- `page_size` int 默认 20，最大 100

响应 `data`：
```json
{
  "page": 1,
  "page_size": 20,
  "total": 2,
  "items": [
    {
      "id": "vid_01HXYZ",
      "title": "示例电影",
      "type": "movie",
      "duration_sec": 5400,
      "size_bytes": 1234567890,
      "resolution": "1920x1080",
      "cover_url": "http://127.0.0.1:8787/api/v1/videos/vid_01HXYZ/cover",
      "created_at": "2026-11-09T10:00:00+08:00",
      "updated_at": "2026-11-09T10:00:00+08:00"
    }
  ]
}
```

## 2. 视频详情

`GET /api/v1/videos/{id}`

响应 `data`：列表字段 + 
```json
{
  "path": "movies/示例电影.mp4",
  "mime": "video/mp4",
  "subtitle_tracks": [
    { "id": "sub_1", "lang": "zh", "label": "简体", "url": "http://127.0.0.1:8787/api/v1/videos/vid_01HXYZ/subtitles/sub_1" }
  ],
  "qualities": [
    { "id": "source", "label": "原画", "width": 1920, "height": 1080 }
  ]
}
```

## 3. 搜索

与列表相同：`GET /api/v1/videos?q=关键词`  
另提供别名：`GET /api/v1/search?q=关键词`（同列表结构）

## 4. 播放地址

当前阶段：**直链文件流**（Range 支持），暂无 m3u8。

`GET /api/v1/videos/{id}/play`

Query：
- `quality` 默认 `source`

响应 `data`：
```json
{
  "play_type": "direct",
  "url": "http://127.0.0.1:8787/api/v1/videos/vid_01HXYZ/stream?quality=source&token=<短时签名或复用Bearer>",
  "expires_in": 3600,
  "headers": {}
}
```

实际拉流：
`GET /api/v1/videos/{id}/stream`  
- 支持 `Range`
- 开发期可用同一 Bearer；后续改为短时签名 query `sig` + `exp`

清晰度：v0.1 仅 `source`（原文件）。转码档位后置。

## 5. 鉴权

- 开发：静态 Bearer token（见本机 `.env` 的 `MEDIA_API_TOKEN`）
- 请求头：`Authorization: Bearer <token>`
- **暂无刷新**；401 时前端提示重新配置 token
- 后续计划：`POST /api/v1/auth/login` → access/refresh JWT（未实现）

## 6. 封面

`GET /api/v1/videos/{id}/cover`  
- 有封面返回图片；无封面 404 或默认占位（前端可本地占位）

## 7. 字幕

`GET /api/v1/videos/{id}/subtitles` → 字幕轨列表  
`GET /api/v1/videos/{id}/subtitles/{sub_id}` → 字幕文件（vtt/srt）

无字幕时列表为空数组。

## 8. 进度上报

`PUT /api/v1/videos/{id}/progress`

Body：
```json
{ "position_sec": 120.5, "duration_sec": 5400, "device_id": "flutter-win-1" }
```

响应：`{ "ok": true, "data": { "saved": true } }`

`GET /api/v1/videos/{id}/progress?device_id=...` 取回进度。

## 9. 上传（前端 / 管理端）

`POST /api/v1/videos/upload`  
`multipart/form-data`：
- `file` 必填
- `title` 可选（默认文件名）
- `type` 可选：`movie`|`episode`|`music` 默认 `movie`

响应 `data`：新建视频详情对象。

文件落盘：`/workspace/media/movies|shows|music/`（持久目录）。

## 10. 删除

`DELETE /api/v1/videos/{id}` → 删除元数据与文件（开发期开放）。

---

## Flutter 对接建议

1. 配置 `baseUrl` + `apiToken`
2. 列表页：`GET /videos`
3. 播放页：先 `GET /videos/{id}/play` 再把 `url` 交给播放器（需带 Bearer 或签名）
4. 定时 `PUT /progress`
5. Bot 电脑无公网入站时，Windows/安卓真机无法直连 `127.0.0.1`；联调阶段可用：
   - 在 Bot 桌面跑模拟器/调试，或
   - 后续把服务部署到有公网/内网 IP 的机器并更新 base URL

有字段要改直接说，我按你的播放器壳调整。
