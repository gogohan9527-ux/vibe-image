# vibe-image — 产品需求文档 (PRD)

## 1. 背景

`demo.py` 已验证可以通过 MomoAPI (`POST https://momoapi.top/v1/images/generations`，模型 `t8-/gpt-image-2`) 完成单次提示词生图并保存到 `images/` 目录。需要在此基础上构建一个工程化的 Web 应用，让用户：

- 在浏览器中以扁平白底 UI 管理"提示词 → 生图"任务；
- 维护可复用的提示词资产；
- 控制后端的并发与排队上限；
- 查看历史记录并与生成图片建立绑定关系。

## 2. 目标

| 序号 | 目标 |
|------|------|
| G1 | 将一次性脚本封装为可长期运行的服务，前后端解耦 |
| G2 | 支持多任务并发 + 队列限流，参数运行时可调 |
| G3 | 提示词作为资产管理，支持新增 / 选择 / 复用 |
| G4 | 配置与密钥与代码分离，模板进库、真实配置不进库 |
| G5 | 历史记录可追溯：每个请求号唯一，与生成图片一一绑定 |

## 3. 非目标

- 不做用户体系（多账号、登录、权限）。
- 不做付费、配额、计费。
- 不做模型微调、prompt 优化、AI 校对。
- 不做云端部署 / 多机分布式（本地单进程即可）。

## 4. 三大核心能力（用户原文）

> **(1)** 配置放在一个配置文件中，新增一个配置模板文件，配置不提交。
> **(2)** 提示词资产放在 `/prompt` 文件夹下，每次调用支持新增 / 选择现有 prompt，每次调用都是一个 prompt 调用。
> **(3)** 支持并发，默认 3，并且能修改并发数；多的 prompt 调用放入队列，超过队列（默认 100，可设置；超过后进入的请求报错），等待线程池空闲再继续调用。生成的文件保留在 `images/` 中不变。

## 5. 角色与场景

**角色：单人开发者 / 创作者**

| 场景 | 描述 |
|------|------|
| S1 创作冲刺 | 一次性提交 50+ 个生图请求，任务自动排队执行，可在前端实时看到进度 |
| S2 模板复用 | 把一段写好的 prompt 存为模板，下次直接选择 |
| S3 资源调控 | API 配额紧张时把并发数调低；闲时调高 |
| S4 任务取消 | 发现某条 prompt 写错，从队列中删除或中断正在跑的任务 |
| S5 历史回看 | 翻看历史，按提示词搜索、下载或重新生成 |

## 6. 功能需求

### 6.1 任务列表页（对应 `assets/page-task.png`）

- 顶部标题"任务列表"+ 副标题"查看您正在生成的、高优先级的任务"。
- 任务卡片，每条显示：
  - 任务序号（任务1、任务2…）+ 任务图标。
  - 提示词原文（截断显示，hover 看全文）。
  - 创建时间。
  - 进度条（百分比，按阶段推进：排队 0% → 调用 10% → 拿到 URL 50% → 下载 80% → 完成 100%）。
  - 缩略图（完成后展示）。
  - 预计剩余时间（基于平均耗时估算）。
  - 操作按钮：暂停/继续（best-effort 取消）、删除。
- 右上角"刷新"按钮（实际数据由 SSE 推送，按钮强制重拉）。
- 任务状态：`queued / running / succeeded / failed / cancelled`，失败显示错误原因 tooltip。

### 6.2 新建任务抽屉（对应 `assets/page-task-new.png`）

抽屉从右侧滑出，字段：

| 字段 | 控件 | 必填 | 说明 |
|------|------|------|------|
| 提示词 | 多行文本框 | 是 | 直接输入或下方"选择模板"自动填入 |
| 选择模板 | Combobox（带搜索） | 否 | 从 `/api/prompts` 拉取，选中后填充提示词 |
| 保存为模板 | Checkbox | 否 | 勾选后将本次提示词写入 `/prompt/prompt_<id>.json` |
| 模型版本 | Select | 是 | 默认 `t8-/gpt-image-2`，可在 config 中扩展 |
| 比例 | Radio 按钮组 | 是 | 1:1 / 16:9 / 9:16 / 4:3，决定 size 默认值 |
| 尺寸 | Select | 是 | `1024x1024` 等，按比例联动 |
| 数量 | Number Input | 是 | 默认 1，每个数量产生一个独立任务 |
| 优先 | Checkbox | 否 | 勾选则插入队列头部 |
| 取消 / 创建任务 | Button | — | 创建任务调用 `POST /api/tasks` |

提交后：
- 后端为数量 N 创建 N 条独立任务记录，每条返回 `task_id`。
- 若提交时队列已满（`queued + running >= queue_cap`），后端返回 HTTP 429，前端弹错误提示并保留抽屉内容。

### 6.3 历史记录页（对应 `assets/page-history.png`）

- 表格列：缩略图、提示词、模型版本、生成数量、生成时间、状态、操作。
- 操作：下载、删除、重新生成（用同样参数复制一条新任务到队列）。
- 顶部：搜索框（按提示词文本模糊匹配）+ 状态筛选下拉（全部 / 成功 / 失败 / 已取消）。
- 分页：默认每页 10 条，底部翻页器。

### 6.4 设置弹窗

由侧边栏"⚙️ 设置"图标触发：

- 最大并发数：Number Input，范围 1–32，默认 3。
- 队列上限：Number Input，范围 1–10000，默认 100。
- 保存按钮调用 `PUT /api/settings`，立即生效（修改并发数会重建线程池，旧任务继续跑完）。

### 6.5 提示词管理

- 抽屉内的"选择模板"= `GET /api/prompts`。
- 列表项 = `prompt_<id>.json` 文件内容：`{ "id": str, "name": str, "content": str, "created_at": iso }`。
- 删除模板：在抽屉模板下拉项右侧点小垃圾桶 → `DELETE /api/prompts/{id}`，对应 JSON 文件被删除。

### 6.6 实时进度

- 前端在 app 启动时打开一个 EventSource 连到 `GET /api/tasks/stream`。
- 后端在每次任务状态/进度变更时推送 `{ task_id, status, progress, image_path? }`。
- 断线由浏览器自动重连，前端不做额外重试逻辑。

## 7. 非功能需求

| 维度 | 要求 |
|------|------|
| 并发 | 默认 3，运行时 1–32 可调；上调时新任务立即享受新并发，下调时不强杀正在跑的线程 |
| 队列 | 默认 100，运行时 1–10000 可调；超过返回 HTTP 429 + JSON `{ "error": "queue_full", "queue_size": N, "cap": M }` |
| 持久化 | SQLite (`data/vibe.db`) 保存任务与历史；图片以 `generated_<task_id>.<ext>` 命名固化在 `images/` |
| 可恢复 | 进程重启后未完成任务标记为 `failed`（reason: `interrupted`），不自动续跑；图片与历史保留 |
| 配置 | `config/config.yaml` 不入库，提供 `config/config.example.yaml` 模板；启动校验缺失字段 |
| 安全 | API key 仅存在于 `config.yaml`，绝不写入日志、响应、错误信息 |
| 性能 | 单次生图耗时取决于上游；本地排队/调度开销 < 50ms |
| 兼容 | Windows 10/11 + Python 3.11+ + Node 18+ |

## 8. 配置 schema

```yaml
# config/config.example.yaml
api:
  base_url: "https://momoapi.top/v1/images/generations"
  api_key: "REPLACE_ME"
  default_model: "t8-/gpt-image-2"
  default_size: "1024x1024"
  default_quality: "low"
  default_format: "jpeg"
  request_timeout_seconds: 120

server:
  host: "127.0.0.1"
  port: 8000
  cors_origins:
    - "http://localhost:5173"

executor:
  default_concurrency: 3
  default_queue_size: 100
  max_concurrency: 32
  max_queue_size: 10000

paths:
  images_dir: "./images"
  prompts_dir: "./prompt"
  database_path: "./data/vibe.db"
```

## 9. 错误语义（关键路径）

| 场景 | HTTP | 响应体 |
|------|------|--------|
| 队列已满 | 429 | `{ "code": "queue_full", "message": "...", "queue_size": N, "cap": M }` |
| 配置缺失 / 启动失败 | 进程退出 | stderr 打印缺失字段 |
| 上游 4xx/5xx | 任务标记 `failed`，`error_message` 存上游响应摘要（脱敏 api key） |
| 取消任务 | 200 | `{ "task_id": "...", "status": "cancelled" }`；若已完成则返回 409 |
| 修改并发数超限 | 400 | `{ "code": "out_of_range", "field": "concurrency" }` |

## 10. 验收标准

- [ ] 三个核心能力（第 4 节）全部实现并可演示。
- [ ] 三个页面在本地浏览器打开后视觉与 `assets/*.png` 基本一致（布局、配色、控件类型）。
- [ ] 设置中调整并发与队列上限即时生效。
- [ ] 队列满时第 N+1 个请求被拒并显示提示。
- [ ] 删除一条排队中任务，该任务不会再被执行。
- [ ] 历史记录里点击"重新生成"会创建一条新任务并出现在任务列表。
- [ ] 重启进程后历史和图片仍然可见。
- [ ] `config/config.yaml`、`prompt/prompt_*.json`（除 sample）、`data/`、`images/*` 全部位于 `.gitignore`。
