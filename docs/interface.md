# vibe-image — 后端 HTTP 接口契约

> 这份文档由 Backend Agent 维护，是 Frontend Agent 的唯一接口真相源。所有路径均挂在 `/api` 前缀下；后端默认监听 `http://127.0.0.1:8000`。

## 0. 通用约定

- **请求 / 响应** 均为 JSON（`Content-Type: application/json`），字符串字段全部 UTF-8。
- **时间戳** 一律 ISO-8601 UTC，例如 `"2026-05-07T12:34:56Z"`。
- **task_id** 是 UUID4 小写字符串。
- **status 取值**：`queued | running | succeeded | failed | cancelled | cancelling`。
- **错误响应** 统一形如：
  ```json
  { "code": "<machine_code>", "message": "<human readable>", ...optional fields }
  ```
  `code` 见 §7。
- CORS：`server.cors_origins` 在 `config.yaml` 中配置（默认包含 `http://localhost:5173`）。

---

## 1. 任务（Tasks）

### 1.1 `POST /api/tasks` — 创建一个或多个任务

请求体：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | `string` | 是 | 提示词原文（最少 1 字符） |
| `prompt_id` | `string \| null` | 否 | 选择的模板 id；仅作记录用 |
| `save_as_template` | `bool` | 否 | 勾选则把本次 prompt 落到 `prompt/prompt_<slug>.json` |
| `template_name` | `string \| null` | 否 | 配合 `save_as_template`，模板显示名（默认取 prompt 前 40 字） |
| `model` | `string \| null` | 否 | 缺省 = `config.api.default_model` |
| `size` | `string \| null` | 否 | 例如 `1024x1024`；缺省取 config |
| `quality` | `"low" \| "medium" \| "high" \| "auto" \| null` | 否 | 仅接受这四个枚举值；缺省时取 `config.api.default_quality`（不传字段或传 `null` 等价） |
| `format` | `string \| null` | 否 | 例如 `jpeg / png`；缺省取 config |
| `n` | `int` | 否 | 1–50，默认 1。每个 n 创建一条独立任务 |
| `priority` | `bool` | 否 | true 时插入队列头部 |

成功响应 `201 Created`：

```json
{
  "tasks": [
    {
      "id": "4c2b1e8a-...-...",
      "prompt_id": null,
      "prompt_text": "A cute cat playing in a garden",
      "model": "t8-/gpt-image-2",
      "size": "1024x1024",
      "quality": "low",
      "format": "jpeg",
      "status": "queued",
      "progress": 0,
      "image_path": null,
      "image_url": null,
      "error_message": null,
      "created_at": "2026-05-07T12:34:56Z",
      "started_at": null,
      "finished_at": null,
      "priority": 0
    }
  ]
}
```

> 任务成功后，`image_path` 是后端绝对路径（运维定位用），`image_url` 是前端可直接用的相对 URL，例如 `"/images/generated_4c2b1e8a-....jpeg"`。前端展示一律用 `image_url`。

错误：
- `429 queue_full`（见 §7）
- `422 validation`（FastAPI 默认）

curl：
```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a cute cat","n":1}'
```

### 1.2 `GET /api/tasks` — 列出活动任务

返回当前 `queued / running / cancelling` 的任务（按 `created_at` 升序）。终态任务请走 `/api/history`。

成功响应 `200`：
```json
{ "tasks": [ TaskItem, TaskItem, ... ] }
```

curl：
```bash
curl http://127.0.0.1:8000/api/tasks
```

### 1.3 `GET /api/tasks/{task_id}` — 单条任务详情

成功响应 `200`：单个 `TaskItem`。

错误：`404 task_not_found`。

curl：
```bash
curl http://127.0.0.1:8000/api/tasks/4c2b1e8a-...
```

### 1.4 `DELETE /api/tasks/{task_id}` — 取消任务

- 若任务在 `queued`：立即移出队列，状态置为 `cancelled`。
- 若任务在 `running`：设置 cancel 事件，状态先变 `cancelling`，worker 收尾后变 `cancelled`。响应里的 `status` 反映此刻的瞬时状态（可能是 `cancelling`）。
- 若任务已是终态：返回 `409 task_not_cancellable`。

成功响应 `200`：
```json
{ "task_id": "4c2b...", "status": "cancelled" }
```

错误：
- `404 task_not_found`
- `409 task_not_cancellable`

curl：
```bash
curl -X DELETE http://127.0.0.1:8000/api/tasks/4c2b1e8a-...
```

### 1.5 `GET /api/tasks/stream/events` — SSE 实时推送

> 注意路径是 `stream/events`（而不是文档草案里的 `stream`），以避开 `/api/tasks/{task_id}` 的路径冲突。

`Content-Type: text/event-stream`。每条事件形如：

```
event: <event_name>
data: <json_payload>

```

事件类型：

| event | 触发时机 | 字段 |
|-------|---------|------|
| `hello` | 连接建立后立即发送一次 | `{}` |
| `status` | 任务状态变更（`queued` / `running` / `cancelling`） | `{ task_id, status, progress }` |
| `progress` | 进度回调（10/50/80） | `{ task_id, progress, status }` |
| `terminal` | 任务进入 `succeeded / failed / cancelled` | `{ task_id, status, progress, image_path?, image_url?, error_message? }` |

`succeeded` 时的 `terminal` 事件示例：
```json
{
  "event": "terminal",
  "task_id": "4c2b1e8a-...-...",
  "status": "succeeded",
  "progress": 100,
  "image_path": "D:/.../images/generated_4c2b1e8a-....jpeg",
  "image_url": "/images/generated_4c2b1e8a-....jpeg"
}
```

外加每 15 秒一次的心跳（注释行 `: ping`），不会有 `event:` 头，浏览器 EventSource 会忽略。

curl（仅查看，不解析）：
```bash
curl -N http://127.0.0.1:8000/api/tasks/stream/events
```

前端用法（推荐）：
```ts
const es = new EventSource("/api/tasks/stream/events");
es.addEventListener("status", (e) => { ... });
es.addEventListener("progress", (e) => { ... });
es.addEventListener("terminal", (e) => { ... });
```

---

## 2. 静态资源 / Static Assets

### 2.1 `GET /images/<filename>` — 任务生成的图片

后端把 `paths.images_dir`（默认 `<repo>/images/`）挂在 `/images` 路径下，由 FastAPI 的 `StaticFiles` 直接提供文件流：

- **路径前缀**：`/images`（注意：这一段不在 `/api` 之下）。
- **文件名规则**：当前生成器写入 `generated_<task_id>.<format>`，例如 `generated_4c2b1e8a-....jpeg`。
- **Content-Type**：由文件扩展名自动推断（`image/jpeg`、`image/png`）。
- **认证**：无（本地工具，整库文件均可读）。
- **错误**：找不到文件时返回 `404 Not Found`（FastAPI 默认，不带 `code` 字段）。

前端无需自己拼绝对路径，直接用 `TaskItem.image_url`（见 §6）。

curl：
```bash
curl -O http://127.0.0.1:8000/images/generated_4c2b1e8a-....jpeg
```

---

## 3. 提示词模板（Prompts）

模板存为 `prompt/prompt_<id>.json`，文件 schema：
```json
{ "id": "moonlit_forest", "name": "月夜森林", "content": "...", "created_at": "2026-05-07T12:34:56Z" }
```

### 3.1 `GET /api/prompts`

```json
{ "prompts": [ PromptItem, ... ] }
```

curl：`curl http://127.0.0.1:8000/api/prompts`

### 3.2 `GET /api/prompts/{prompt_id}`

`200` → `PromptItem`；`404 prompt_not_found`。

### 3.3 `POST /api/prompts`

请求体：
```json
{ "name": "月夜森林", "content": "moonlit forest with fireflies", "id": null }
```
`id` 可选；缺省由 `name` slug 化得出，重名追加 `-2 / -3 / ...`。

成功 `201` → `PromptItem`。

curl：
```bash
curl -X POST http://127.0.0.1:8000/api/prompts \
  -H "Content-Type: application/json" \
  -d '{"name":"月夜森林","content":"moonlit forest with fireflies"}'
```

### 3.4 `DELETE /api/prompts/{prompt_id}`

成功 `204`（无响应体）。

错误：
- `404 prompt_not_found`
- `409 prompt_conflict`（试图删除内置 `sample`）

---

## 4. 设置（Settings）

### 4.1 `GET /api/settings`
```json
{
  "concurrency": 3,
  "queue_cap": 100,
  "max_concurrency": 32,
  "max_queue_size": 10000
}
```

### 4.2 `PUT /api/settings`

请求体（两个字段都是可选）：
```json
{ "concurrency": 4, "queue_cap": 200 }
```

成功 `200`：返回更新后的 settings 快照（同 §4.1）。

错误：`400 out_of_range`（包含 `field` 字段，值 `concurrency` 或 `queue_cap`）。

curl：
```bash
curl -X PUT http://127.0.0.1:8000/api/settings \
  -H "Content-Type: application/json" \
  -d '{"concurrency":4,"queue_cap":200}'
```

---

## 5. 历史记录（History）

### 5.1 `GET /api/history`

Query 参数：
| 参数 | 默认 | 说明 |
|------|------|------|
| `q` | — | 提示词文本模糊匹配（LIKE %q%） |
| `status` | 全部终态 | `succeeded / failed / cancelled / all` |
| `page` | `1` | 1-based |
| `page_size` | `10` | 1–100 |

成功响应 `200`：
```json
{
  "items": [ TaskItem, ... ],
  "total": 42,
  "page": 1,
  "page_size": 10
}
```

只返回终态任务（`succeeded / failed / cancelled`）。

curl：
```bash
curl 'http://127.0.0.1:8000/api/history?q=cat&status=succeeded&page=1&page_size=10'
```

### 5.2 `DELETE /api/history/{task_id}` — 从历史记录中删除某条终态任务

路径参数：`task_id`（UUID）。

行为：
- 任务不存在 → `404 task_not_found`。
- 任务处于活动态（`queued / running / cancelling`）→ `409 task_active`，提示先调 `DELETE /api/tasks/{task_id}` 取消。本端点 **不会** 隐式触发取消。
- 否则尽力 `unlink` 对应的渲染图（若 `image_path` 缺失或文件不在亦不会报错），删除 SQLite 行，返回 `204 No Content`，无响应体；不发任何 SSE 事件。

错误：
- `404 task_not_found`
- `409 task_active`

curl：
```bash
curl -X DELETE http://127.0.0.1:8000/api/history/4c2b1e8a-0000-0000-0000-000000000001
```

---

## 6. 健康检查

`GET /api/health` → `{ "status": "ok" }`。

---

## 7. 数据类型定义

### TaskItem
```ts
{
  id: string;
  prompt_id: string | null;
  prompt_text: string;
  model: string;
  size: string;
  quality: string;
  format: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "cancelling";
  progress: number;            // 0–100
  image_path: string | null;   // 后端绝对路径（运维 / 调试用），前端不要直接拼到 <img>
  image_url: string | null;    // 例如 "/images/generated_<task_id>.jpeg"；前端直接 <img :src> 用
  error_message: string | null;
  created_at: string;          // ISO-8601 UTC
  started_at: string | null;
  finished_at: string | null;
  priority: number;            // 0 普通 / 1 优先
}
```

### PromptItem
```ts
{
  id: string;
  name: string;
  content: string;
  created_at: string;
}
```

---

## 8. 错误码一览

| HTTP | code | 触发 | 额外字段 |
|------|------|------|----------|
| 400 | `out_of_range` | 设置值越界 | `field`: `"concurrency" \| "queue_cap"` |
| 404 | `task_not_found` | 任务不存在 | — |
| 404 | `prompt_not_found` | 模板不存在 | — |
| 409 | `task_not_cancellable` | 任务已终态 | `task_id`, `status` |
| 409 | `task_active` | 试图从历史里删一条仍活动中的任务 | — |
| 409 | `prompt_conflict` | 试图删除 `sample` | — |
| 429 | `queue_full` | 队列已满 | `queue_size`, `cap` |
| 502 | `upstream_error` | 上游 API 报错 | — |
| 500 | `vibe_error` | 其它已捕获后端错误 | — |
| 422 | (FastAPI 默认) | 请求体校验失败 | `detail` 数组 |

错误响应统一 JSON：
```json
{ "code": "queue_full", "message": "Queue is full (100/100).", "queue_size": 100, "cap": 100 }
```

---

## 9. 启动与端点清单

启动后端后，OpenAPI 文档：`http://127.0.0.1:8000/docs`。

完整端点清单（共 14 条 + 1 个静态挂载）：

| Method | Path |
|--------|------|
| POST | `/api/tasks` |
| GET | `/api/tasks` |
| GET | `/api/tasks/{task_id}` |
| DELETE | `/api/tasks/{task_id}` |
| GET | `/api/tasks/stream/events` |
| GET | `/api/prompts` |
| GET | `/api/prompts/{prompt_id}` |
| POST | `/api/prompts` |
| DELETE | `/api/prompts/{prompt_id}` |
| GET | `/api/settings` |
| PUT | `/api/settings` |
| GET | `/api/history` |
| DELETE | `/api/history/{task_id}` |
| GET | `/api/health` |
| GET | `/images/{filename}` *(StaticFiles 挂载，详见 §2)* |
