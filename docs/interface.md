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

**[已弃用 / DEPRECATED at 2026-05-09 — 请使用下方 v2 (§10.2)]** 旧版本通过请求体直接传 `encrypted_api_key` / `base_url`。自 2026-05-09 起改为 `provider_id` + `key_id` + `model`，凭据由后端 Provider 仓储集中管理。下方旧定义保留以备查 / 历史日志比对。

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

> 自 2026-05-09 起新增 7 条 `/api/providers/*`、改动 `POST /api/tasks` 与 `GET /api/config/status`，详见 §10。
> 自 2026-05-08 起新增 `PUT /api/prompts/{id}` 与 `POST /api/tasks` 的 `title` 字段，详见下方 §9.5 Addendum。

### 9.5 2026-05-08 Addendum — Prompts CRUD + Task title

> 本节是 prompt-template-db 这一轮的接口增量；§3 / §1.1 / §10 仍是基础定义，本节仅补充新增 / 改动。

#### 9.5.1 [NEW] `PUT /api/prompts/{prompt_id}`

部分更新一条模板的 `name` / `content`。两者皆为可选，但至少要传一个。

请求体：
```json
{ "name": "moonlit forest v2", "content": "moonlit forest with fireflies and a moon" }
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `string` | 否 | 提供时 `min_length=1, max_length=120` |
| `content` | `string` | 否 | 提供时 `min_length=1` |

响应 `200`：更新后的完整 `PromptItem`（schema 同 §3.2）。

错误：

| 状态 | code | 触发条件 |
|------|------|----------|
| 400 | `prompt_update_invalid` | `name` / `content` 都未传（或都为 null） |
| 404 | `prompt_not_found` | `prompt_id` 在 DB 中不存在 |
| 422 | (FastAPI 校验) | 提供了字段但为空字符串 |

#### 9.5.2 [CHANGED] `POST /api/tasks` — 新增可选字段 `title`

在 §1.1（v1）请求体之上新增（v2 §10.2 同样适用，无冲突）：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `title` | `string \| null` | 否 | `null` | 任务标题；trim 后非空才算用户提供。空 / null / 全空白 → 后端兜底 `prompt[:30]`。最大长度建议 60（前端 maxlength 控制）。 |

后端 `task_manager.submit()` 的 title 计算：
- 用户提供 → 直接用，并设内部「title 已锁定」标志位。
- 用户未提供 → `prompt_text.strip()[:30]` 兜底；标志「未锁定」。
- generator 完成路径若响应字段含 `revised_prompt` 等可用文本，且 title 未锁定 → `text[:30]` 覆盖兜底。

#### 9.5.3 [CHANGED] `TaskItem` — 新增 `title` 字段

在所有列出（§1.2 / §1.3 / §5.1）与 history 路径中，`TaskItem` 多一个字段：

| 字段 | 类型 | 备注 |
|------|------|------|
| `title` | `string \| null` | 旧 task 行（feature 上线前已存在）此字段为 `null`，前端容忍即可 |

> 注：SSE `terminal` 事件载荷**不**携带 `title`。前端如需最新 title，请通过 `GET /api/tasks/{id}` 或 `GET /api/history` 查询。

#### 9.5.4 错误码增量

| HTTP | code | 端点 | 触发条件 |
|------|------|------|---------|
| 400 | `prompt_update_invalid` | `PUT /api/prompts/{id}` | 请求体两个字段都为空 |

#### 9.5.5 兼容性

- 既有不传 `title` 的请求**完全不受影响**——后端走兜底分支，行为可预测（`prompt[:30]`）。
- 旧任务（DB 升级前已落库）`title` 列为 NULL，前端按缺省渲染。
- `GET/POST/DELETE /api/prompts` 路径不变；后端将存储从 JSON 文件换成 `prompt_templates` 表对前端透明。

---

## 10. 2026-05-09 Addendum — Providers + Mode + Tasks v2

> 本节是 plugin-providers-mode-config 这一轮的接口增量，由 `docs/interface.draft.md`（已合入并删除）合并而来。
>
> §10 内的端点定义优先于上文同名/同路径的旧定义。冲突时旧定义在原位标 `[已弃用 / DEPRECATED]`，新定义放本节并打 `[v2 — 自 2026-05-09]` 前缀。
>
> 错误响应仍统一形如 `{ "code": "...", "message": "...", ...optional fields }`。

### 10.0 通用约定补充

#### 10.0.1 凭据传输

- 通过既有 `GET /api/config/public-key` 获取 RSA-2048 OAEP-SHA256 公钥（PEM, SubjectPublicKeyInfo）。
- 前端 `crypto.ts` 新增 `encryptObject(obj: Record<string,string>) -> Record<string,string>`：对每个 value 调用现有 `encryptApiKey` (RSA-OAEP) 得到 base64 ciphertext，组合为同 key 名称的 dict。
- 后端 `crypto.py::CryptoManager.decrypt_dict(payload)` 逐 value 解密为明文 dict，仅在 `add_key` 流程内消费、用完即弃，绝不落日志、错误信息、响应体。
- 后端进程重启会换新 RSA 公私钥；前端发现 `/api/config/public-key` 返回的 PEM 与缓存不同，应清掉本地的 ciphertext 缓存（如果有）。

#### 10.0.2 启动模式 (mode)

- 启动模式由 `GET /api/config/status`（详见 §10.4）的 `mode` 字段返回（`"normal"` 或 `"demo"`）。前端不再询问 `api_key_configured` —— 该字段已删除。

---

### 10.1 Providers (新增模块)

#### 10.1.1 [NEW] `GET /api/providers`

列出所有内置 Provider 的元数据 + 当前配置摘要。本期始终包含且仅包含 `momo`。

**响应 200**：
```json
{
  "providers": [
    {
      "id": "momo",
      "display_name": "MOMO",
      "default_base_url": "https://momoapi.top/v1",
      "credential_fields": [
        { "name": "api_key", "label": "API Key", "secret": true, "required": true }
      ],
      "config": {
        "base_url": "https://momoapi.top/v1",
        "default_model": "t8-/gpt-image-2",
        "default_key_id": "abc-123-..."
      },
      "key_count": 1
    }
  ]
}
```

`config` 在用户从未编辑该 Provider 时为 `null`；前端在 `null` 情况下应使用 `default_base_url` 作为 placeholder。

curl：`curl http://127.0.0.1:8000/api/providers`

#### 10.1.2 [NEW] `PUT /api/providers/{provider_id}/config`

部分更新 Provider 的配置。三个字段都可选，但请求体至少要包含一个，否则 422。

请求体：
```json
{ "base_url": "...", "default_model": "...", "default_key_id": "..." }
```

响应 200：返回更新后的 `ProviderConfigOut`：
```json
{ "base_url": "...", "default_model": "...", "default_key_id": "..." }
```

错误：
- `400 unknown_provider` — `provider_id` 不在 `PROVIDER_REGISTRY`
- `422` — 请求体校验（包括"三字段都为 null"）

#### 10.1.3 [NEW] `GET /api/providers/{provider_id}/keys`

列出该 Provider 下所有 Key 元数据（**不含**凭据明文/密文）。

响应 200：
```json
{
  "keys": [
    { "id": "abc-123-...", "provider_id": "momo", "label": "personal", "created_at": "2026-05-09T12:34:56Z" }
  ]
}
```

错误：`400 unknown_provider`。

#### 10.1.4 [NEW] `POST /api/providers/{provider_id}/keys`

新增一条 Key。提交时凭据字段已用 RSA 公钥按字段加密。

请求体：
```json
{ "label": "personal", "encrypted_credentials": { "api_key": "<base64 RSA-OAEP ciphertext>" } }
```

服务端会：
1. 解密 `encrypted_credentials` 得到明文 dict；
2. 校验 dict 的 keys 与 Provider 的 `credential_fields[i].name` 一致（多余字段忽略，必填字段缺失返回 400）；
3. AES-256-GCM 加密落库（normal）或入内存（demo）；
4. **同步**触发一次 models refresh —— 但失败不会回滚 Key 添加，只在响应里把 `models_refresh_error` 字段填上 upstream 摘要。

响应 201：
```json
{
  "key": { "id": "abc-123-...", "provider_id": "momo", "label": "personal", "created_at": "2026-05-09T12:34:56Z" },
  "models": [ { "id": "t8-/gpt-image-2", "display_name": null, "fetched_at": "..." } ],
  "models_refresh_error": null
}
```

错误：
- `400 unknown_provider`
- `400 credential_decrypt_failed` — RSA 解密失败（公钥/私钥错配）
- `400 invalid_credentials` — 必填字段缺失（带 `missing_fields: ["api_key", ...]`）
- 注意：refresh 步骤失败时**不**抛 502，而是把错误塞 `models_refresh_error` 字段返回；前端可据此提示用户"凭据已保存但拉取模型失败，请稍后手动 Refresh"。

#### 10.1.5 [NEW] `DELETE /api/providers/{provider_id}/keys/{key_id}`

级联删除：移除 Key 行 + 该 Key 的 cached models，并清空对应 `default_key_id`。

响应 204：无响应体。

错误：
- `400 unknown_provider`
- `404 key_not_found`

注意：服务端**不**校验"是否还有未完成的任务在引用该 Key"。前端如需阻止删除应先查活动任务。

#### 10.1.6 [NEW] `GET /api/providers/{provider_id}/models?key_id=<kid>`

返回该 Key 已缓存的模型列表（不会触发 upstream 调用）。Query `key_id` 必填。

响应 200：
```json
{ "models": [ { "id": "t8-/gpt-image-2", "display_name": null, "fetched_at": "2026-05-09T12:34:56Z" } ] }
```

错误：`400 unknown_provider` / `400 key_not_found`（Query 中的 key 在 store 里不存在）。`models` 可为空数组。

#### 10.1.7 [NEW] `POST /api/providers/{provider_id}/models/refresh`

强制从 upstream 重新拉取模型列表并替换缓存。

请求体：`{ "key_id": "abc-123-..." }`

响应 200：刷新后的 `ProviderModelMeta[]`。

错误：
- `400 unknown_provider`
- `400 key_not_found`
- `502 upstream_error` — `list_models` 调用失败（带 `message` 摘要，不含 Authorization）

---

### 10.2 [v2 — 自 2026-05-09] `POST /api/tasks`

替代 §1.1 的旧定义。

**REMOVED 字段**：`encrypted_api_key`、`base_url`。
**ADDED 必填字段**：`provider_id` (string)、`key_id` (string)、`model` (string，必填，不再缺省回落到 config)。

请求体（新）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | `string` | 是 | 提示词原文 |
| `prompt_template_id` | `string \| null` | 否 | （注：v1 中字段名为 `prompt_id`；v2 沿用 `prompt_template_id`，后端兼容两者）|
| `save_as_template` | `bool` | 否 | |
| `provider_id` | `string` | **是** | 例如 `"momo"` |
| `key_id` | `string` | **是** | 来自 `GET /api/providers/{id}/keys` |
| `model` | `string` | **是** | 来自 `GET /api/providers/{id}/models` 或 Provider config 的 `default_model` |
| `size` | `string \| null` | 否 | 默认 `"1024x1024"` |
| `quality` | `"low" \| "medium" \| "high" \| "auto" \| null` | 否 | 默认 `"low"` |
| `format` | `string \| null` | 否 | 默认 `"jpeg"` |
| `n` | `int` | 否 | 1–50，默认 1 |
| `priority` | `bool` | 否 | |

响应 201：与既有 `TaskItem` 一致，新增 `provider_id` / `key_id` 字段（旧任务为 null）：

```json
{
  "tasks": [
    {
      "id": "...",
      "prompt": "a cat",
      "model": "t8-/gpt-image-2",
      "size": "1024x1024",
      "quality": "low",
      "format": "jpeg",
      "status": "queued",
      "progress": 0,
      "image_path": null,
      "image_url": null,
      "error_message": null,
      "created_at": "2026-05-09T12:34:56Z",
      "started_at": null,
      "finished_at": null,
      "priority": 0,
      "provider_id": "momo",
      "key_id": "abc-123-..."
    }
  ]
}
```

错误（新增 / 修改）：
- `400 unknown_provider` — `provider_id` 不在 `PROVIDER_REGISTRY`，extra: `provider_id`
- `400 provider_not_configured` — provider 没有任何 Key（或没有 base_url 配置），extra: `provider_id`
- `400 key_not_found` — `key_id` 在该 Provider 的 store 中不存在，extra: `key_id`
- `429 queue_full` — 沿用 §1.1
- `422 validation` — 沿用 FastAPI 默认

curl：
```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"prompt":"a cat","provider_id":"momo","key_id":"abc-123-...","model":"t8-/gpt-image-2","n":1}'
```

---

### 10.3 Tasks 其它端点

`GET /api/tasks` / `GET /api/tasks/{id}` / `DELETE /api/tasks/{id}` / `GET /api/tasks/stream/events` 行为不变。`TaskItem` 响应 schema 多了 `provider_id` / `key_id` 字段（旧任务为 null）。

---

### 10.4 [CHANGED] `GET /api/config/status`

> 旧文档未覆盖此端点；本节即为持久化定义。`GET /api/config/public-key` 不变。

**REMOVED 字段（相对未文档化的旧实现）**：`api_key_configured`、`base_url`。
**ADDED 字段**：
- `mode`: `"normal" | "demo"`（来自 `config.mode`）
- `any_provider_configured`: `bool`（任意一个 Provider 至少有一个 Key 即为 true）

响应 200：
```json
{ "mode": "normal", "any_provider_configured": false }
```

curl：`curl http://127.0.0.1:8000/api/config/status`

---

### 10.5 数据类型 (新增 / 扩展)

```ts
// CredField — Provider 在 GET /api/providers 中声明的字段元数据
export interface CredField {
  name: string;
  label: string;
  secret: boolean;     // true 时前端用 password input
  required: boolean;
}

// ProviderConfigOut
export interface ProviderConfigOut {
  base_url: string;
  default_model: string | null;
  default_key_id: string | null;
}

// ProviderSummary — GET /api/providers 列表项
export interface ProviderSummary {
  id: string;
  display_name: string;
  default_base_url: string;
  credential_fields: CredField[];
  config: ProviderConfigOut | null;
  key_count: number;
}

// ProviderKeyMeta — 永远不含凭据明文/密文
export interface ProviderKeyMeta {
  id: string;
  provider_id: string;
  label: string;
  created_at: string;            // ISO-8601 UTC
}

// ProviderModelMeta
export interface ProviderModelMeta {
  id: string;
  display_name: string | null;
  fetched_at: string;            // ISO-8601 UTC
}

// AddKeyRequest
export interface AddKeyRequest {
  label: string;
  encrypted_credentials: Record<string, string>;  // value = base64 RSA-OAEP ciphertext
}

// AddKeyResponse
export interface AddKeyResponse {
  key: ProviderKeyMeta;
  models: ProviderModelMeta[];
  models_refresh_error: string | null;
}

// UpdateProviderConfigRequest
export interface UpdateProviderConfigRequest {
  base_url?: string;
  default_model?: string;
  default_key_id?: string;
}

// RefreshModelsRequest
export interface RefreshModelsRequest { key_id: string; }

// ConfigStatusResponse — GET /api/config/status (重写)
export interface ConfigStatusResponse {
  mode: "normal" | "demo";
  any_provider_configured: boolean;
}

// TaskItem 的 v2 增量字段（其余字段同 §7）
// provider_id: string | null;
// key_id:      string | null;
```

---

### 10.6 错误码 (新增)

| HTTP | code | 触发 | 额外字段 |
|------|------|------|----------|
| 400 | `unknown_provider` | `provider_id` 不在 `PROVIDER_REGISTRY` | `provider_id` |
| 400 | `provider_not_configured` | provider 没有任何 Key 但被任务引用 | `provider_id` |
| 400 | `key_not_found` | 指定 `key_id` 不存在（POST /api/tasks、refresh、GET /models） | `key_id` |
| 400 | `invalid_credentials` | `add_key` 时必填字段缺失 | `missing_fields: string[]` |
| 400 | `credential_decrypt_failed` | RSA-OAEP 解密失败 | — |
| 404 | `key_not_found` | `DELETE /api/providers/{id}/keys/{kid}` 命中不存在的 key | `key_id` |
| 502 | `upstream_error` | `list_models` / `refresh` upstream 失败 | `message`（脱敏） |

> 注：`key_not_found` 在 400 与 404 都出现，是因为 DELETE 上下文按 REST 语义返回 404，其它上下文（`POST /api/tasks` 提交时 / `refresh` 时）按"输入校验失败"返回 400。前端按 `code` 区分即可，HTTP status 只是辅助。

---

### 10.7 已删除的接口表面 (Removed surface)

下列字段/行为在本轮**已删除**：

- `TaskCreateRequest.encrypted_api_key`、`TaskCreateRequest.base_url`（见 §10.2）
- `ConfigStatusResponse.api_key_configured`、`ConfigStatusResponse.base_url`（见 §10.4）
- `MissingApiKeyError` (`api_key_missing` 400) — 替换为 `provider_not_configured` / `key_not_found`
- 配置文件中的 `api:` 段（`api_key`、`base_url`、`default_model`、…）
- 环境变量 `VIBE_API_KEY`、`VIBE_BASE_URL`

---

### 10.8 端点清单（合并后总览）

| Method | Path | 备注 |
|--------|------|------|
| POST | `/api/tasks` | v2（§10.2，旧定义 §1.1 已弃用） |
| GET | `/api/tasks` | 不变 |
| GET | `/api/tasks/{task_id}` | 不变 |
| DELETE | `/api/tasks/{task_id}` | 不变 |
| GET | `/api/tasks/stream/events` | 不变 |
| GET | `/api/prompts` 等 | 不变 |
| GET | `/api/settings`、PUT | 不变 |
| GET | `/api/history`、DELETE | 不变 |
| GET | `/api/health` | 不变 |
| GET | `/api/config/status` | 重写（§10.4）|
| GET | `/api/config/public-key` | 不变 |
| GET | `/api/providers` | 新增（§10.1.1） |
| PUT | `/api/providers/{provider_id}/config` | 新增（§10.1.2） |
| GET | `/api/providers/{provider_id}/keys` | 新增（§10.1.3） |
| POST | `/api/providers/{provider_id}/keys` | 新增（§10.1.4） |
| DELETE | `/api/providers/{provider_id}/keys/{key_id}` | 新增（§10.1.5） |
| GET | `/api/providers/{provider_id}/models` | 新增（§10.1.6） |
| POST | `/api/providers/{provider_id}/models/refresh` | 新增（§10.1.7） |
| GET | `/images/{filename}` | StaticFiles，不变 |

> 自 2026-05-09（II）起新增 `POST /api/uploads/temp`、`POST /api/tasks` 加入参考图字段、`TaskItem` / `ProviderSummary` 增字段，详见 §11。自 2026-05-11 起参考图主字段升级为 `input_image_paths`，旧 `input_image_path` 保留兼容。

---

## 11. 2026-05-09 Addendum (II) — img2img 支持

> 本节是 img2img-support 这一轮的接口增量，由 `docs/interface.draft.md`（已合入并删除）合并而来。
>
> §11 内的端点定义优先于上文同名/同路径的旧定义，**仅当本节显式列出的字段或错误码与上文不同时**生效；其余字段（`prompt` / `provider_id` / `key_id` / `model` / `size` / …）沿用 §10.2。
>
> 错误响应仍统一形如 `{ "code": "...", "message": "...", ...optional fields }`。

### 11.1 [NEW] `POST /api/uploads/temp`

上传一张图生图的参考图，返回 storage key 和可预览 URL。前端可多次调用本端点拿到多个 `input_image_path`，再把这些 key 组成 `input_image_paths` 数组传给 `POST /api/tasks`。

- **Content-Type**: `multipart/form-data`
- **请求字段**：
  - `file` （**必填**，binary）— 仅接受 `image/png` / `image/jpeg` / `image/webp`，按 MIME + 文件头双重校验。

后端语义：
1. 读全文件至内存，超过 `defaults.max_upload_bytes`（默认 `10 * 1024 * 1024` = 10 MiB；可通过 `VIBE_DEFAULTS_MAX_UPLOAD_BYTES` env 覆盖）→ 413。
2. magic-byte 校验确认是真 PNG / JPEG / WEBP，否则 → 400。
3. 计算 `sha1(content)` 作为去重键；若 active `StorageBackend.exists("temp/<sha1>.<ext>")` 为 true 则跳过写入（同内容重复上传幂等）。
4. 扩展名按 sniff 结果取（不信用户提交的文件名/MIME）：PNG → `.png`，JPEG → `.jpg`，WEBP → `.webp`。

**响应 200**：
```json
{
  "input_image_path": "temp/9f86d081884c7d659a2feaa0c55ad015a3bf4f1b.png",
  "url": "/images/temp/9f86d081884c7d659a2feaa0c55ad015a3bf4f1b.png"
}
```

> 注：`input_image_path` 用 forward slash 形式（即使后端是 Windows）。新前端把多个返回值组成 `input_image_paths`；旧 client 仍可把单个值回填到 `input_image_path`。`url` 由 active storage backend 生成：local 为 `/images/temp/...`，OSS 模式为 public URL 或预签名 URL。

**错误**：

| HTTP | code | 触发 | 额外字段 |
|------|------|------|----------|
| 400 | `invalid_upload` | 缺 `file` 字段 / 非允许 MIME / 头校验未过 | `reason: string` |
| 413 | `upload_too_large` | 字节数 > `max_upload_bytes` | `max_bytes: int`, `actual_bytes: int` |

**curl 示例**：
```bash
curl -F file=@photo.png http://127.0.0.1:8000/api/uploads/temp
```

**安全约束**：
- 错误信息中**不**回显完整原始文件名给前端（仅响应 sha1 短哈希），避免暴露文件系统细节。
- local 模式下 `images_dir/temp/` 在后端启动时确保存在（`config.images_temp_dir`）；OSS 模式下对象写入 `<prefix>temp/<sha1>.<ext>`。
- 上传文件**不**会在任务结束后自动清理（保留以便历史回看）；GC 留作后续工单。

---

### 11.2 [CHANGED] `POST /api/tasks` — 增量字段 `input_image_paths`

在 §10.2（v2，2026-05-09）的基础上新增参考图字段。`input_image_paths` 是 canonical 多图字段；`input_image_path` 是旧单图兼容字段。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `input_image_paths` | `string[] \| null` | 否 | 由 `POST /api/uploads/temp` 返回的 key 数组，元素形如 `"temp/<sha1>.<ext>"`，**必须以 `temp/` 开头**。非空数组时任务走 img2img 通路。 |
| `input_image_path` | `string \| null` | 否 | 旧字段；后端归一化为 `[input_image_path]`。若与 `input_image_paths` 同时传且内容冲突，返回 `400 input_image_conflict`。 |

其余请求字段与 §10.2 完全一致。

后端语义（与 §10.2 v2 流程的差异）：
1. 后端先归一化参考图字段：
   - 若只传 `input_image_path`，转为单元素数组。
   - 若只传 `input_image_paths`，原样使用非空元素。
   - 若二者同时传且不等价，返回 `400 input_image_conflict`。
2. 若归一化后的数组非空：
   - 每个 key 必须位于 `temp/` 命名空间，不能是绝对路径，不能包含 `..` 或反斜杠；否则 → 400 `input_image_not_found`。
   - 每个 key 必须通过 active `StorageBackend.exists(key)` 校验；local 模式查本地文件，OSS 模式查桶对象；不存在 → 400 `input_image_not_found`。
   - 选中 provider 的 `supports_image_input` 必须为 `true`；否则 → 400 `provider_capability_unsupported`。
3. 任务内部只使用 `input_image_paths`。执行时由 `StorageBackend.url/read` 构造 provider 需要的参考图 URL / bytes，不再拼 `images_dir/temp/...` 本地路径。
4. `n > 1` 时每条任务共用同一组 `input_image_paths`（不复制文件）。

**响应 201**（与 §10.2 一致，但 `TaskItem` 增量见 §11.3）。

**错误**（新增 / 沿用）：

| HTTP | code | 触发 | 额外字段 |
|------|------|------|----------|
| 400 | `input_image_conflict` | `input_image_path` 与 `input_image_paths` 同时传且不等价 |  |
| 400 | `input_image_not_found` | 某个参考图 key 不合法或在 active storage 中不存在 | `input_image_path: string` |
| 400 | `provider_capability_unsupported` | 任务带参考图但选中 provider 的 `supports_image_input == false` | `provider_id: string`, `capability: "image_input"` |
| 400 | `unknown_provider` / `provider_not_configured` / `key_not_found` | 沿用 §10.2 |  |
| 429 | `queue_full` | 沿用 §1.1 |  |

**curl 示例**：
```bash
# 1. 上传参考图
RESP=$(curl -s -F file=@cat.png http://127.0.0.1:8000/api/uploads/temp)
PATH_=$(echo "$RESP" | python -c "import sys,json;print(json.load(sys.stdin)['input_image_path'])")

# 2. 提交带图任务
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d "{\"prompt\":\"redraw as oil painting\",\"provider_id\":\"momo\",\"key_id\":\"abc-123\",\"model\":\"t8-/gpt-image-2\",\"input_image_paths\":[\"$PATH_\"]}"
```

---

### 11.3 [CHANGED] `TaskItem` — 增量字段 `input_image_paths` / `input_image_urls`

`TaskItem` schema 在 §7 + §10.5（v2）字段基础上新增多图字段，并保留旧单图字段作为派生兼容值：

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `input_image_paths` | `string[] \| null` | DB JSON 列 | canonical 参考图 key 数组；旧任务或无参考图任务为 `null` |
| `input_image_urls` | `string[] \| null` | computed | active storage backend 为每个 key 生成的 URL 数组 |
| `input_image_path` | `string \| null` | compatibility | `input_image_paths[0]`；旧 client 用 |
| `input_image_url` | `string \| null` | compatibility | `input_image_urls[0]`；旧 client 用 |

完整示例（带图任务）：
```json
{
  "id": "task-xyz",
  "prompt": "redraw as oil painting",
  "title": "redraw as oil painting",
  "model": "t8-/gpt-image-2",
  "size": "1024x1024",
  "quality": "low",
  "format": "jpeg",
  "status": "succeeded",
  "progress": 100,
  "image_path": "/abs/path/images/generated_task-xyz.jpeg",
  "image_url": "/images/generated_task-xyz.jpeg",
  "input_image_paths": ["temp/9f86d0...png", "temp/abcd12...webp"],
  "input_image_urls": ["/images/temp/9f86d0...png", "/images/temp/abcd12...webp"],
  "input_image_path": "temp/9f86d0...png",
  "input_image_url": "/images/temp/9f86d0...png",
  "error_message": null,
  "created_at": "2026-05-09T12:34:56Z",
  "started_at": "2026-05-09T12:34:57Z",
  "finished_at": "2026-05-09T12:35:30Z",
  "priority": 0,
  "provider_id": "momo",
  "key_id": "abc-123-..."
}
```

`TaskItem` 在所有列出 / 单查路径里都会带这些字段；旧任务字段为 `null`，前端按缺省处理（不渲染输入图）。SSE terminal payload 仍只保证输出图字段（`image_path` / `image_url`）。

---

### 11.4 [CHANGED] `GET /api/providers` — `ProviderSummary.supports_image_input`

`ProviderSummary` 在 §10.5 基础上新增一个布尔字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `supports_image_input` | `boolean` | `true` 表示该 Provider 实现了 `build_image_edit_request`（img2img 入口），前端可据此点亮"参考图"上传 UI；`false` 时禁用并提示"当前 Provider 不支持图生图"。 |

本期内置 provider 的取值：
- `"momo"` → `supports_image_input: true`

未来新接入的 provider 默认 `false`，需在 provider 实现里显式声明。

`ProviderSummary` 在所有列出位置都附带本字段；增字段，旧 client 忽略即可，无向后兼容问题。

---

### 11.5 数据类型 (TS)

```ts
/** Response of POST /api/uploads/temp. */
export interface TempUploadResponse {
  /** Server-side relative path, e.g. "temp/<sha1>.png". Re-submit verbatim
   *  in POST /api/tasks's `input_image_paths` array, or legacy
   *  `input_image_path` field for single-image clients. */
  input_image_path: string;
  /** Public URL for inline preview, e.g. "/images/temp/<sha1>.png". */
  url: string;
}

// TaskItem 的 (II) 增量字段（其余字段同 §7 + §10.5）：
//   input_image_path: string | null;
//   input_image_url:  string | null;   // compatibility: first URL
//   input_image_paths: string[] | null;
//   input_image_urls:  string[] | null;

// ProviderSummary 的 (II) 增量字段（其余字段同 §10.5）：
//   supports_image_input: boolean;

// CreateTaskRequest 的 (II) 增量字段（其余字段同 §10.2）：
//   input_image_paths?: string[] | null; // canonical
//   input_image_path?: string | null;    // legacy single-image alias
```

---

### 11.6 错误码增量

新增 5 个 code（其余沿用既有 §8 + §10.6 错误码表）：

| HTTP | code | 端点 | 触发条件 | 额外字段 |
|------|------|------|---------|---------|
| 400 | `invalid_upload` | `POST /api/uploads/temp` | 文件缺失 / MIME 不允许 / 头校验失败 | `reason: string` |
| 413 | `upload_too_large` | `POST /api/uploads/temp` | 字节数超过 `defaults.max_upload_bytes` | `max_bytes: int`, `actual_bytes: int` |
| 400 | `input_image_conflict` | `POST /api/tasks` | `input_image_path` 与 `input_image_paths` 同时传且不等价 |  |
| 400 | `input_image_not_found` | `POST /api/tasks` | 参考图 key 不合法或在 active storage 中不存在 | `input_image_path: string` |
| 400 | `provider_capability_unsupported` | `POST /api/tasks` | 任务带参考图，但 provider 的 `supports_image_input == false` | `provider_id: string`, `capability: string`（本期固定为 `"image_input"`）|

---

### 11.7 兼容性 / 边界

- 既有不带参考图字段的任务流程**完全不受影响**——字段是可选的；旧 client 不发字段即走文生图分支，行为与 v2 一致。
- 旧 client 传 `input_image_path` 仍可创建单参考图任务；后端写入 canonical `input_image_paths`，并同步保留旧首图字段。
- 启动迁移会把历史 `input_image_path` 回填到 `input_image_paths = ["..."]`；不触发网络上传。
- 上传文件不会在任务结束时被自动 GC；多次任务可复用同一个参考图 key（`POST /api/uploads/temp` 内置去重）。
- 上传不做速率限制（本期单机工具，留作后续）。

---

### 11.8 端点清单（合并后总览）

| Method | Path | 备注 |
|--------|------|------|
| POST | `/api/uploads/temp` | 新增（§11.1）— multipart |
| POST | `/api/tasks` | v2 + img2img 增量字段（§11.2）|
| GET | `/api/providers` | 新增 `supports_image_input` 字段（§11.4） |
| 其余 §10.8 端点 | | 不变 |

---

## §12 Demo 模式 Token 鉴权协议 **[v1 — 自 2026-05-10]**

> 本节为横切关注点（cross-cutting concern），不增加新端点。仅在 `mode: demo` 时生效；`mode: normal` 时本节协议完全不激活。

### 12.1 概述

`mode: demo` 启动时，后端 `DemoAuthMiddleware` 拦截所有 `/api/*` 请求，要求携带有效 demo token。无效或缺失 token 返回 `HTTP 401`。

### 12.2 Token 传递方式

客户端从以下两种方式中选一种传递：

**方式 A — HTTP Header（推荐，用于普通 fetch 请求）**
```
X-Demo-Token: <token>
```

**方式 B — Query Parameter（EventSource/SSE 必须用此方式）**
```
?demo_token=<token>
```

两种方式等价；中间件先查 Header，再查 Query Param。

### 12.3 豁免（demo 模式下无需 token）

- `OPTIONS` 请求（CORS preflight）— 始终放行
- 不以 `/api/` 开头的路径（如 `/images/...`、`/`）— 不检查

### 12.4 401 响应体

```json
{
  "code": "demo_required",
  "message": "未获得 Demo 访问权限"
}
```

### 12.5 受保护端点

§10.8 + §11.8 中所有 `/api/*` 端点均受保护。关键端点的 token 传递方式：

| Endpoint | Token 方式 |
|----------|-----------|
| 所有 `GET/POST/PUT/DELETE /api/*` | Header `X-Demo-Token` |
| `GET /api/tasks/stream/events` (SSE) | **Query Param** `?demo_token=` |

### 12.6 TypeScript 类型

无新端点。`ErrorBody.code` 可取值 `"demo_required"`：

```typescript
if (error instanceof ApiError && error.code === 'demo_required') {
  isDemoDenied.value = true;  // 展示全屏"未受邀"遮罩
}
```

### 12.7 curl 示例

```bash
# 携带 Header（demo 模式）
curl -H "X-Demo-Token: your-token" http://localhost:8000/api/health
# → {"status": "ok"}

# SSE 流携带 query param
curl "http://localhost:8000/api/tasks/stream/events?demo_token=your-token"

# 无 token → 401
curl http://localhost:8000/api/health
# → {"code":"demo_required","message":"未获得 Demo 访问权限"}
```

### 12.8 Token 管理（后端参考）

- 首次 demo 模式启动自动生成，存入 `data/demo_token.txt`（gitignored）
- `config.yaml` 设置 `secret_key: "your-token"` 可固定 token
- 启动日志打印：`Demo mode active — access token: <token>`
- 分享 URL 格式：`http://<host>:<frontend-port>?demo_token=<token>`
