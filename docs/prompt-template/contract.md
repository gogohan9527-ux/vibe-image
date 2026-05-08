# 提示词模板 DB 化 + 任务 title 字段 — Frontend ↔ Backend 契约

> Backend lane 在 B6 写出，Frontend lane 必须以本文件为权威来源。
> 所有字段使用 **snake_case**。所有时间戳为 ISO-8601 UTC（`Z` 后缀）字符串。
> 所有 API 路径都带 `/api` 前缀（FastAPI router 在 `app.main` 中以 `prefix="/api"` 挂载）。
> 错误响应统一形如 `{"code": "<machine_code>", "message": "<human msg>", ...extra}`（见每个端点的错误小节）。

---

## 1. `GET /api/prompts`

列出全部模板。

**请求**：无请求体，无查询参数。

**响应** `200`：
```json
{
  "prompts": [
    {
      "id": "sample",
      "name": "示例：花园里的猫",
      "content": "A cute cat playing in a garden",
      "created_at": "2026-05-07T00:00:00Z"
    }
  ]
}
```

字段：
| 字段 | 类型 | 说明 |
|------|------|------|
| `prompts[].id` | string | 模板唯一 id（slug，下划线分隔，冲突自动追加 `-2`/`-3`） |
| `prompts[].name` | string | 显示名 |
| `prompts[].content` | string | 模板正文 |
| `prompts[].created_at` | string (ISO-8601) | 创建时间 |

排序：`created_at DESC`。

---

## 2. `POST /api/prompts`

新建一条模板。

**请求体**：
```json
{
  "name": "moonlit forest",
  "content": "moonlit forest with fireflies",
  "id": "moonlit_forest"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | `min_length=1, max_length=120` |
| `content` | string | 是 | `min_length=1` |
| `id` | string | 否 | 缺省时由 `name` 推导 slug；冲突自动追加 `-2`/`-3` |

**响应** `201`（与 `GET /api/prompts/{id}` 同 schema）：
```json
{
  "id": "moonlit_forest",
  "name": "moonlit forest",
  "content": "moonlit forest with fireflies",
  "created_at": "2026-05-08T03:14:15Z"
}
```

**错误**：
| 状态 | code | 触发条件 |
|------|------|----------|
| 422 | (FastAPI 校验) | `name` / `content` 缺失或为空 |

---

## 3. `PUT /api/prompts/{prompt_id}`（**新增**）

部分更新一条模板的 `name` / `content`。两者皆为可选，但至少要传一个。

**Path 参数**：`prompt_id`（string）。

**请求体**：
```json
{
  "name": "moonlit forest v2",
  "content": "moonlit forest with fireflies and a moon"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 否 | 提供时 `min_length=1, max_length=120` |
| `content` | string | 否 | 提供时 `min_length=1` |

**响应** `200`（更新后的完整 `PromptItem`）：
```json
{
  "id": "moonlit_forest",
  "name": "moonlit forest v2",
  "content": "moonlit forest with fireflies and a moon",
  "created_at": "2026-05-08T03:14:15Z"
}
```

**错误**：
| 状态 | code | 触发条件 |
|------|------|----------|
| 400 | `prompt_update_invalid` | `name` / `content` 都未传（或都为 null） |
| 404 | `prompt_not_found` | `prompt_id` 在 DB 中不存在 |
| 422 | (FastAPI 校验) | 提供了字段但为空字符串 |

错误体示例：
```json
{ "code": "prompt_update_invalid", "message": "name or content required" }
```

---

## 4. `DELETE /api/prompts/{prompt_id}`

删除模板。`sample` 模板受保护，删不掉。

**响应** `204`（无 body）。

**错误**：
| 状态 | code | 触发条件 |
|------|------|----------|
| 404 | `prompt_not_found` | id 不存在 |
| 409 | `prompt_conflict` | `prompt_id == "sample"` |

错误体示例：
```json
{ "code": "prompt_conflict", "message": "Cannot delete the bundled sample prompt." }
```

---

## 5. `POST /api/tasks`（**新增字段：`title`**；其余字段保留）

提交 1 ~ N 个生成任务。

**请求体**：
```json
{
  "prompt": "a cute cat in a garden",
  "title": "我的猫",
  "prompt_id": "sample",
  "save_as_template": false,
  "template_name": null,
  "model": "t8-/gpt-image-2",
  "size": "1024x1024",
  "quality": "low",
  "format": "jpeg",
  "n": 1,
  "priority": false
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `prompt` | string | 是 | — | `min_length=1` |
| `title` | string \| null | 否 | `null` | 任务标题；trim 后非空才算用户提供。空 / null / 全空白 → 后端兜底 `prompt[:30]`。最大长度建议 60（前端 maxlength 控制）。 |
| `prompt_id` | string \| null | 否 | `null` | 可选关联模板 id |
| `save_as_template` | bool | 否 | `false` | 为 true 时把本次 prompt 写入 `prompt_templates` 表 |
| `template_name` | string \| null | 否 | `null` | 仅 `save_as_template=true` 时使用；缺省时取 `prompt[:40]` |
| `model` | string \| null | 否 | 配置默认 | |
| `size` | string \| null | 否 | 配置默认 | |
| `quality` | `"low" \| "medium" \| "high" \| "auto"` \| null | 否 | 配置默认 | |
| `format` | string \| null | 否 | 配置默认 | |
| `n` | int | 否 | 1 | `1..50` |
| `priority` | bool | 否 | `false` | true → 队列头插 |

**响应** `201`：返回 `n` 条新任务。
```json
{
  "tasks": [
    {
      "id": "0c2f9e7e-...",
      "prompt_id": "sample",
      "prompt_text": "a cute cat in a garden",
      "title": "我的猫",
      "model": "t8-/gpt-image-2",
      "size": "1024x1024",
      "quality": "low",
      "format": "jpeg",
      "status": "queued",
      "progress": 0,
      "image_path": null,
      "image_url": null,
      "error_message": null,
      "created_at": "2026-05-08T03:14:15Z",
      "started_at": null,
      "finished_at": null,
      "priority": 0
    }
  ]
}
```

**错误**：
| 状态 | code | 触发条件 |
|------|------|----------|
| 422 | (FastAPI 校验) | `prompt` 缺失或空 |
| 429 | `queue_full` | 队列已满，body 含 `queue_size`、`cap` |

---

## 6. `GET /api/tasks` （活跃任务列表，包含 `title`）

返回 `status ∈ {queued, running, cancelling}` 的任务，按 `created_at` 升序。

**响应** `200`：
```json
{
  "tasks": [
    { "...": "TaskItem 同 POST 响应中每条" }
  ]
}
```

每条 `tasks[]` 即下方 §9 定义的 `TaskItem`。

---

## 7. `GET /api/tasks/{task_id}`

**响应** `200`：单条 `TaskItem`（含 `title`）。
**错误** `404 task_not_found`。

---

## 8. `GET /api/tasks/stream/events`（SSE）

事件流（不变；事件载荷不携带 `title`，与原契约一致）。事件类型：
- `event: hello` — 初始 hello，data `{}`。
- `event: status` — `{ task_id, status, progress }`。
- `event: progress` — `{ task_id, progress, status }`（`status="running"`）。
- `event: terminal` — `{ task_id, status, progress, image_path?, image_url?, error_message? }`。

如前端需要任务的最新 `title`，请通过 `GET /api/tasks/{id}` 或 `GET /api/history` 查询。

---

## 9. `GET /api/history`（包含 `title`）

**查询参数**：`q`（string, 可选）、`status`（`succeeded|failed|cancelled|all`，可选）、`page`（int ≥1，默认 1）、`page_size`（int 1..100，默认 10）。

**响应** `200`：
```json
{
  "items": [
    {
      "id": "...",
      "prompt_id": null,
      "prompt_text": "a cat",
      "title": "a cat",
      "model": "t8-/gpt-image-2",
      "size": "1024x1024",
      "quality": "low",
      "format": "jpeg",
      "status": "succeeded",
      "progress": 100,
      "image_path": "/abs/path/generated_xxx.jpeg",
      "image_url": "/images/generated_xxx.jpeg",
      "error_message": null,
      "created_at": "2026-05-08T03:14:15Z",
      "started_at": "2026-05-08T03:14:16Z",
      "finished_at": "2026-05-08T03:14:18Z",
      "priority": 0
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 10
}
```

---

## 10. 类型契约：`TaskItem`

跨多个端点共享：
| 字段 | 类型 | 备注 |
|------|------|------|
| `id` | string | UUID |
| `prompt_id` | string \| null | |
| `prompt_text` | string | |
| `title` | string \| null | **新增**。旧 task 行（feature 上线前已存在）此字段为 null，前端需容忍 |
| `model` | string | |
| `size` | string | |
| `quality` | string | |
| `format` | string | |
| `status` | `"queued" \| "running" \| "succeeded" \| "failed" \| "cancelled" \| "cancelling"` | |
| `progress` | int | 0..100 |
| `image_path` | string \| null | 后端绝对路径，前端不直接用 |
| `image_url` | string \| null | 计算字段：`/images/<basename>`（前端用这个） |
| `error_message` | string \| null | 仅 `failed` 时有 |
| `created_at` | string | ISO-8601 |
| `started_at` | string \| null | |
| `finished_at` | string \| null | |
| `priority` | int | 0 / 1 |

---

## 11. 备注

- `title` 写入与读出都是 trim 后的字符串；后端在 `task_manager.submit` 中根据「是否有非空 title」决定锁定标志（`title_locked`），未锁定时 generator 完成路径若有可用文本字段会回填 `text[:30]`，否则保持兜底。前端不需要感知锁定标志。
- `save_as_template=true` 时若 `template_name` 缺省，后端用 `prompt[:40]` 作为 name；现有行为不变。
- `prompt_templates` 表的初始化是手动命令 `python -m app.scripts.init_db`（后端自带 CLI），前端无需调用任何接口去触发。
