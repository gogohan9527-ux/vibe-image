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

---

## 2026-05-08 Addendum — 提示词模板 DB 化 + 任务 title 字段

> 本次迭代把模板存储从文件系统迁到 SQLite，并在新建任务流程中加入可选标题。
>
> 计划文件：`C:\Users\PC\.claude\plans\agent-skill-abundant-kernighan.md`。

### 1. 背景

提示词模板原本存在 `/prompt/prompt_*.json`（一份模板一个文件），通过 `Storage.list_prompts/save_prompt/delete_prompt` 直接读写文件系统。`NewTaskDrawer.vue` 已有「模板下拉」与「保存为模板」勾选项，但保存逻辑未接入提交流程；任务表无 `title` 字段，无法在列表中区分相似 prompt 的任务。本期把模板存储迁到 SQLite，并在新建任务流程中加入可选标题（不填则自动兜底）。

### 2. 目标

| 序号 | 目标 |
|------|------|
| G1 | 新增 `prompt_templates` 表，所有模板 CRUD 走 DB |
| G2 | 提供独立的初始化方法把 `/prompt/*.json` 同步入库（首次手动调用，不删除 JSON） |
| G3 | `tasks` 表新增 `title` 字段，POST /api/tasks 支持可选 title |
| G4 | NewTaskDrawer 顶部新增标题输入框；勾选「保存为模板」时落库到新表 |
| G5 | title 为空时：先用 `prompt[:30]` 兜底；若 generator 完成响应中有可用文本则覆盖 |
| G6 | 侧边导航新增「模板配置」入口，提供模板列表 + 新建 / 编辑 / 删除 UI |

### 3. 非目标

- 不在任务卡 / 历史页展示 title（仅存库与回包）
- 不做模板下拉的搜索 / 过滤
- 不删除 `/prompt/*.json` 文件（保留作为种子）
- 不做模板版本化、收藏、分类、批量导入导出
- 不引入文本 LLM 调用专门生成标题

### 4. 用户原话

> 1. 新建任务时 如果勾选将本次提示词保存为模板则存库到提示词模板表
> 2. 项目初始化时，默认将/prompt模板表的数据初始化到模板表中（用户补充：「python独立一个初始化方法 第一次启动时手动去调用这个方法 不删除json 记得加到readme中」）
> 3. 新建任务的UI变更 支持标题 选择模板从库里查 如果不填标题 看是不是有好的办法自动生成标题 或者通过AI的response来保存标题（用户补充：「13结合 如果3没有回填就用1」）
> 4. 「保留现有将本次任务建为模板 这个勾选项」

### 5. 功能需求要点

#### 5.1 后端 — 提示词模板表

- 新表 `prompt_templates(id TEXT PK, name TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)`，建表 SQL 与现有 `tasks` 一同维护，启动时若不存在则自动创建。
- 现有 `tasks` 表新增 `title TEXT NULL`，使用 `ALTER TABLE … ADD COLUMN` 兼容已有库。
- `Storage.list_prompts / get_prompt / save_prompt / delete_prompt` 全部改为读写 `prompt_templates` 表；`delete_prompt('sample')` 仍受保护。

#### 5.2 后端 — 独立初始化方法

- 新增 `Storage.init_db()`：补齐缺失数据库 schema 后扫描 `<project_root>/prompt/prompt_*.json`，按 `id` 主键导入（已存在则跳过）；返回写入条数与跳过条数。
- 提供 CLI 入口：`python -m app.scripts.init_db`。
- 启动时（lifespan）**不再** 自动调用 `ensure_sample_prompt`；改为日志提示用户手动跑。
- README 新增「首次初始化提示词模板」段落。

#### 5.3 后端 — 任务 title

- `TaskCreateRequest` 新增 `title: Optional[str]`（trim 后非空才算用户提供）。
- `TaskItem` 新增 `title: Optional[str]`，所有响应路径都带上。
- `task_manager.submit()` 在创建 row 时计算 title：
  - 用户提供 → 直接用，并设内部「title 已锁定」标志。
  - 用户未提供 → 取 `prompt_text.strip()[:30]` 兜底；标志「未锁定」。
- 生成完成路径：若响应字段含 `revised_prompt` 等可用文本，且 title 未锁定，则 `text[:30]` 覆盖兜底；找不到字段则 no-op。

#### 5.4 后端 — 模板编辑接口

- 新增 `PUT /api/prompts/{id}`：请求体 `{name?: string, content?: string}`，二者都可选但至少要传一个；返回更新后的 `PromptItem`。
- `Storage.update_prompt(prompt_id, name=None, content=None)`：写库；id 不存在抛 404。

#### 5.5 前端 — NewTaskDrawer 标题输入 + 提交透传

- prompt 文本域上方新增 `<el-input v-model="title">`，placeholder：「留空将自动生成（取 prompt 前 30 字）」，maxlength=60，非必填。
- `submit()`：trim 后 title 非空才加入 payload；勾选 saveAsTemplate 时把 `save_as_template` + `template_name`（用户填了才传）一并提交。
- 关闭抽屉 / 提交成功后清空 title、saveAsTemplate、templateName。

#### 5.6 前端 — 模板配置页

- 新增路由 `/templates` → `frontend/src/views/PromptTemplatesView.vue`。
- `AppSidebar.vue` 加 nav 项「模板配置」。`activeKey` 计算改为按 path 反查（避免硬编码）。
- 顶部按钮「新建模板」打开 dialog（name 必填 maxlength 60 / content 必填 textarea maxlength 2000）。
- 表格列：名称 / 内容预览（截断 60 字 + tooltip）/ 创建时间 / 操作（编辑 / 删除）；编辑复用同 dialog；删除走 `el-popconfirm`；`sample` 删除按钮 disabled。

### 6. 错误语义（关键路径）

| 场景 | HTTP | 响应体 / 行为 |
|------|------|---------------|
| POST /api/prompts name/content 空 | 400 | `{detail: "name and content required"}` |
| DELETE /api/prompts/sample | 400 | `{detail: "sample prompt is protected"}` |
| init_db 找到非法 JSON | exit 0 | warn + 跳过；最后打印总结 |
| init_db 重复执行 | exit 0 | skip 已存在；输出 imported=0 / skipped=N |
| POST /api/tasks 不传 title | 201 | DB 中 title = `prompt[:30]` |
| POST /api/tasks 传 title="  " | 201 | 视为空，走兜底 |
| PUT /api/prompts/{id} body 为空对象 | 400 | `{detail: "name or content required"}` |
| PUT /api/prompts/{id} id 不存在 | 404 | `{detail: "prompt not found"}` |

### 7. 验收标准

- [x] 新建空数据库 → 启动 → 调用 `python -m app.scripts.init_db`，`prompt_templates` 出现 `prompt/*.json` 全部条目；重复执行写入 0、跳过 N。
- [x] `POST /api/tasks -d '{"prompt":"..."}'` → DB tasks.title = `prompt[:30]`；`save_as_template=true,template_name="..."` → DB prompt_templates 多一条。
- [x] 前端：不填 / 填 / 勾保存模板三条路径都通；模板配置页 CRUD 完整。
- [x] `cd backend && pytest` 全绿（59 passed in 2.82s）。

---

## 2026-05-09 Addendum — 插件化 API 凭据 & 多 Provider 支持

> 本次迭代针对开源场景重构凭据/上游配置:把硬编码的单一 OpenAI 兼容端点 + yaml/env 凭据,改为运行期可管理的"内置 Provider + 多 Key + 模型缓存"。
>
> 全文实现细节与决策见计划文件 `C:\Users\PC\.claude\plans\api-key-base-url-bubbly-tarjan.md`。

### A.1 新增目标

| 序号 | 目标 |
|------|------|
| G6 | 凭据从 yaml/env 全面下沉到运行期管理,UI 即所见即所得 |
| G7 | 支持多 Provider(本期仅内置 MOMO);Provider 抽象层为后续接入 Gemini/Stability 留接口 |
| G8 | 同一 Provider 可配置多个 Key (label),任务提交显式选 Key |
| G9 | 配置三层覆盖 (`docker > env > yaml`) 适用于 **所有** 配置项 |
| G10 | 区分 `normal` (持久化) 与 `demo` (内存) 启动模式 |
| G11 | 任务卡片直接展示失败返回原因 |

### A.2 新增功能需求

#### A.2.1 Providers 配置页(新增,路由 `/providers`)

- 列表展示所有内置 Provider(本期仅 `momo`),不需要"安装",默认全有,只可"配置"。
- 每个 Provider 卡片可:
  - 编辑 `base_url`(默认 `https://momoapi.top/v1`,存 origin 不带 endpoint path)
  - 维护 Keys 列表:label + 凭据字段(由 Provider 的 `credential_fields` 决定;MOMO 仅需 `api_key`)。删除、设默认。
  - 维护 Models 缓存:首次添加 Key 后自动拉取并入库;手动 Refresh 按钮。
- 增删 Key 的流程:
  1. 用户输入字段 → 前端用 RSA 公钥逐字段加密 → POST `/api/providers/{id}/keys`
  2. 后端解密 → AES-GCM 加密入库(`normal`)或入内存(`demo`)
  3. 自动同步触发 `POST /api/providers/{id}/models/refresh`
  4. 成功后该 Provider 卡片渲染最新 model 列表

#### A.2.2 新建任务流程改造(`NewTaskDrawer`)

- 增加三级联动选择:**Provider → Key → Model**(前两个必选,Model 从缓存中选,允许搜索)。
- 没有任何 Provider 配置过 Key 时,Drawer 显示空状态 + 一键跳转 `/providers`。
- 提交时不再传 `encrypted_api_key`/`base_url`,改传 `provider_id` + `key_id` + `model`。

#### A.2.3 任务失败原因展示

- `TaskCard.vue`:`status === 'failed'` 时在卡片底部增加红色错误行(13px),展示截断后的 `error_message`,悬停 tooltip 看完整,带"复制"按钮。
- `HistoryView.vue`:同步加失败原因展示。

#### A.2.4 启动模式开关 (`VIBE_MODE`)

| 模式 | 默认 | Provider 配置/Key/Models 仓储 | 任务/历史/模板 |
|------|------|------------------------------|----------------|
| `normal` | ✅ | SQLite + AES-GCM at-rest | SQLite |
| `demo` | | 进程内存 (重启即清) | SQLite (照旧) |

来源:env > yaml(顶层 `mode`)> 默认。docker-compose 通过 `environment:` 注入。

#### A.2.5 配置三层覆盖

所有配置项支持 `os.environ` 覆盖 yaml,命名规则 `VIBE_<SECTION>_<KEY>` 全大写嵌套用 `_`。

| yaml 路径 | env 变量 |
|---|---|
| `mode` | `VIBE_MODE` |
| `server.host` | `VIBE_SERVER_HOST` |
| `server.port` | `VIBE_SERVER_PORT` |
| `server.cors_origins` | `VIBE_SERVER_CORS_ORIGINS` (CSV) |
| `executor.default_concurrency` | `VIBE_EXECUTOR_DEFAULT_CONCURRENCY` |
| `executor.default_queue_size` | `VIBE_EXECUTOR_DEFAULT_QUEUE_SIZE` |
| `executor.max_concurrency` | `VIBE_EXECUTOR_MAX_CONCURRENCY` |
| `paths.images_dir` | `VIBE_PATHS_IMAGES_DIR` |
| `paths.database_path` | `VIBE_PATHS_DATABASE_PATH` |
| `paths.prompts_dir` | `VIBE_PATHS_PROMPTS_DIR` |
| `defaults.request_timeout_seconds` | `VIBE_DEFAULTS_REQUEST_TIMEOUT_SECONDS` |
| `secret_key`(顶层特判) | `VIBE_SECRET_KEY` |

Docker-compose `environment:` 与 shell env 在 Python 端同源 (`os.environ`);Docker 自身保证 `-e` 优先于 compose,这点在 README 文档化。

### A.3 非功能需求新增

| 维度 | 要求 |
|------|------|
| 凭据 at-rest | `normal` 模式 AES-256-GCM,每条 key 独立 nonce;主密钥 `VIBE_SECRET_KEY` env > `data/master.key`(自动生成,文件权限 0600) |
| 凭据传输 | 沿用 RSA-OAEP(`/api/config/public-key`),扩展为 `decrypt_dict` 解多字段 |
| 安全 | `error_message` 不得含 `Authorization` header;上游响应做 200 字符摘要 |
| Breaking | 旧 `config.yaml.api.*`、`VIBE_API_KEY`、`VIBE_BASE_URL` 移除;旧 task 行 `provider_id`/`key_id` 为 NULL,UI 标 "(legacy)" |

### A.4 配置 schema (重写)

```yaml
# config/config.example.yaml
mode: normal              # normal | demo;可被 VIBE_MODE 覆盖

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

defaults:
  request_timeout_seconds: 120
```

### A.5 错误语义新增

| 场景 | HTTP | 响应体 |
|------|------|--------|
| Provider 未配置 / Key 不存在 | 400 | `{ "code": "provider_not_configured", "provider_id": "..." }` 或 `{ "code": "key_not_found", "key_id": "..." }` |
| `list_models` 上游报错 | 502 | `{ "code": "upstream_error", "message": "..." }` |
| Provider id 未识别 | 400 | `{ "code": "unknown_provider", "provider_id": "..." }` |

### A.6 验收标准 (本次迭代)

- [ ] 进入页面不弹任何凭据框(空 `normal` 库 / 空 `demo` 内存均如此)
- [ ] `/providers` 页面 MOMO 卡片可编辑 base_url、增删 Key、刷新 Models
- [ ] 添加 Key 后自动触发 models/refresh,模型列表立即可见
- [ ] 新建任务三级联动 Provider → Key → Model,提交并生成成功
- [ ] 任务失败时 TaskCard / HistoryView 卡片展示后端 `error_message`
- [ ] 同一 Provider 可加两个不同 label 的 Key,各自任务在历史中可区分
- [ ] `normal` 模式重启进程,Provider 配置 + Keys + Models 仍在
- [ ] `demo` 模式重启进程,以上全清空(任务历史照旧 SQLite)
- [ ] 配置三层覆盖:同时设 yaml + env,以 env 为准;同时设 env + docker-compose `environment:`,以容器最终 env 为准
- [ ] `data/vibe.db` 中 `provider_keys.encrypted_credentials` 列为二进制密文(非明文)
- [ ] 旧 `config.yaml.api.*` 字段被忽略;旧 task 行带 `(legacy)` 标识展示

---

## 2026-05-09 Addendum (II) — 图生图 (img2img) 支持

> 本次迭代：在文生图基础上新增"图生图"通路。用户可上传一张参考图，prompt + 图片一起送给 provider；provider 协议增加可选的"图生图入口"，未实现的 provider 会直接报错。本期仅 momo 插件落地。
>
> 计划文件：`C:\Users\PC\.claude\plans\images-temp-provider-prompt-momo-resume-sleepy-squid.md`。

### B.1 新增目标

| 序号 | 目标 |
|------|------|
| G12 | 在不破坏文生图通路的前提下，提供图生图模式（参考图 + prompt → 输出图） |
| G13 | Provider 抽象暴露"图生图入口"为可选能力；运行期由元数据 `supports_image_input` 公开，前端可据此 gate UI |
| G14 | 上传图片落盘到 `images_dir/temp/`，与生成结果共用 `/images` 静态服务 |

### B.2 非目标（本期）

- 不做 mask（OpenAI edits 也支持 mask，本期不暴露）。
- 不做多图输入（仅支持一张参考图）。
- 不做 temp 目录定时 GC（预留下个工单）。
- 不修改现有 provider 列表（仅扩 momo）。

### B.3 新增功能需求

#### B.3.1 上传接口（新增）

`POST /api/uploads/temp`（multipart `file` 字段）：
- 仅接受 `image/png | image/jpeg | image/webp`，按 MIME + 文件头双重校验。
- 限制 `≤ max_upload_bytes`（配置项，默认 `10 * 1024 * 1024`）。
- 落盘命名：`temp/<sha1(content)>.<ext>`；同内容文件去重，不重复落盘。
- 响应：`{ "input_image_path": "temp/<sha1>.<ext>", "url": "/images/temp/<sha1>.<ext>" }`。

错误：
- `400 invalid_upload`（非图片 / 无文件 / MIME 不允许）
- `413 upload_too_large`（超过 `max_upload_bytes`）

#### B.3.2 任务接口扩展

`POST /api/tasks` 请求体新增可选字段：
- `input_image_path: string | null` — 由 `/api/uploads/temp` 返回，形如 `temp/<sha1>.<ext>`，**必须以 `temp/` 开头**且实际存在；后端用 `Path.resolve()` 比 `images_dir.resolve()` 前缀，防止越权读其他目录。

`TaskItem` 响应新增：
- `input_image_path: string | null` — 后端持久化字段。
- `input_image_url: string | null`（computed）— 形如 `/images/temp/<sha1>.<ext>`，前端直接 `<img :src>` 用。

校验：若 `input_image_path` 非空且选中 provider 的 `supports_image_input == false` → `400 provider_capability_unsupported`。

#### B.3.3 Providers 元数据扩展

`GET /api/providers` 每条 `ProviderSummary` 新增：
- `supports_image_input: boolean` — 由 Provider 类属性派生；momo 为 `true`，未来新接入插件默认 `false`。

#### B.3.4 NewTaskDrawer 改造

- 在提示词区下方新增"参考图"小节：拖放 / 点击选择 / 预览缩略图 / 移除按钮。
- 选中文件后立刻调 `POST /api/uploads/temp`；失败 toast 错误并允许重试。
- 当 `selectedProvider.supports_image_input === false` 时：上传区禁用，提示"当前 Provider 不支持图生图"。
- 提交任务时，若已上传图片则把 `input_image_path` 一并传入 `POST /api/tasks`。

#### B.3.5 TaskCard 显示输入图

- 当 `task.input_image_url` 存在：在生成结果缩略图旁加一个小输入图缩略图（同尺寸或略小），便于用户回看是哪张图生成的。
- hover 显示完整大小预览（与现有输出图行为一致）。
- 历史页 `HistoryView.vue` 同步加输入图列（小缩略图）。

### B.4 配置 schema 增量

```yaml
defaults:
  request_timeout_seconds: 120
  max_upload_bytes: 10485760   # 10 MiB；可被 VIBE_DEFAULTS_MAX_UPLOAD_BYTES 覆盖
```

`paths.images_dir` 不变；后端启动时确保 `images_dir/temp/` 存在。

### B.5 错误语义增量

| HTTP | code | 触发 | 额外字段 |
|------|------|------|----------|
| 400 | `provider_capability_unsupported` | 任务带 `input_image_path` 但 provider `supports_image_input == false` | `provider_id`, `capability: "image_input"` |
| 400 | `invalid_upload` | 上传非图片 / 类型不允许 / 空文件 | `reason` |
| 413 | `upload_too_large` | 超过 `max_upload_bytes` | `max_bytes`, `actual_bytes` |
| 400 | `input_image_not_found` | 任务引用的 `input_image_path` 在磁盘上不存在或越界 | `input_image_path` |

### B.6 验收标准（本次迭代）

- [ ] 添加 momo provider key 后，新建任务抽屉里的"参考图"区可点亮。
- [ ] 上传 PNG（< 10MB）成功，drawer 内显示缩略图预览。
- [ ] 上传 20MB 文件 → 后端 413、前端 toast；上传 .txt → 后端 400、前端 toast。
- [ ] 提交任务（带参考图）→ 成功生成，TaskCard 同时显示输入图与输出图缩略图。
- [ ] HistoryView 终态任务可见输入图列。
- [ ] 临时把 momo 的 `supports_image_input` 改 `false`，提交带图任务 → 前端 toast `provider_capability_unsupported`。
- [ ] 重启进程后旧任务（`input_image_path` 为 NULL）卡片正常，无 JS 报错。
- [ ] `pytest backend/tests/` 全绿（含本轮 + 旧测试）。
- [ ] `npm run build` 类型通过。

