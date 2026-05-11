# vibe-image — 项目规章与说明

本文档定义工程结构、命名约定、协作边界与本地运行流程。所有贡献者（含 AI 子智能体）必须遵守。

## 1. 仓库结构

```
vibe-image/
├── backend/                 # 后端 (Python / FastAPI) — Backend Agent 负责
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── schemas.py
│   │   ├── api/             # 路由层
│   │   ├── core/            # 业务核心：task_manager / generator / storage
│   ├── tests/
│   └── requirements.txt
├── frontend/                # 前端 (Vue 3 + Vite + TS + Element Plus) — Frontend Agent 负责
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── prompt/                  # 提示词资产 (.json)
│   └── prompt_sample.json   # 示例，进库
├── images/                  # 生成的图片 (gitignored)
│   └── .gitkeep
├── data/                    # SQLite db (gitignored)
│   └── .gitkeep
├── config/
│   ├── config.example.yaml  # 进库
│   └── config.yaml          # gitignored
├── docs/
│   ├── prd.md
│   ├── explanation.md       # 本文件
│   ├── interface.md         # 由 Backend Agent 编写并维护
│   └── todolist.md          # 双 lane 进度追踪
├── assets/                  # UI 参考截图（保持只读）
├── demo.py                  # 原始演示脚本（保留作参考，不再调用）
├── requirements.txt         # 旧顶层依赖（保留），新依赖写入 backend/requirements.txt
├── .gitignore
├── CLAUDE.md
└── README.md
```

## 2. Lane 与所有权（防止两个 Agent 互踩）

| Lane | 可写路径 | 不可写路径 |
|------|---------|-----------|
| **Backend Agent** | `backend/**`、`config/**`、`prompt/prompt_sample.json`、`docs/interface.md`、`docs/todolist.md`（仅 B 行）、根目录 `.gitignore`（仅添加自身相关条目）、`README.md`（后端段落） | `frontend/**`、`assets/**`、`docs/prd.md`、`docs/explanation.md` |
| **Frontend Agent** | `frontend/**`、`docs/todolist.md`（仅 F 行）、`README.md`（前端段落） | `backend/**`、`config/**`、`prompt/**`、`docs/interface.md`、`docs/prd.md`、`docs/explanation.md` |

公共文件（PRD、explanation、PNG 截图）**只读**。如需调整，先在对话中提出，由 orchestrator 决定。

## 3. 命名约定

| 实体 | 规则 | 示例 |
|------|------|------|
| `task_id` | UUID4 字符串（小写带连字符） | `4c2b1e8a-...` |
| `prompt_id` | 小写蛇形 slug，最大 48 字符；同名追加 `-2/-3` | `dreamy_sunset` |
| 提示词文件 | `prompt/prompt_<prompt_id>.json` | `prompt/prompt_dreamy_sunset.json` |
| 图片文件 | `images/generated_<task_id>.<ext>` | `images/generated_4c2b....jpeg` |
| Python 模块 | snake_case；类 PascalCase；常量 UPPER_SNAKE | — |
| TS / Vue | 组件 PascalCase；其余 camelCase；store 文件 `useXxxStore.ts` | — |

## 4. 编码规范

### 4.1 后端

- Python 3.11+，全部加类型注解。
- 严禁 `from x import *`；禁止裸 `except:`。
- 配置只能通过 `app.config.get_config()` 读取，不允许散落 `os.getenv`。
- API key、上游响应中可能含密的字段绝不进日志。
- 业务异常用自定义 `VibeError` 抛出；FastAPI 全局 handler 转 HTTP。
- 风格：默认 `ruff` + `black`（如未安装则保持 PEP 8 手写一致）。

### 4.2 前端

- 全 TypeScript，严禁 `any`（实在需要写 `unknown` + 类型守卫）。
- 仅使用 Element Plus 组件；不得引入第二个 UI 库。
- 网络请求统一走 `src/api/client.ts`，禁止页面内裸 `fetch`。
- 状态管理用 Pinia，按域拆 store：`useTaskStore` / `usePromptStore` / `useSettingsStore`。
- 样式：组件级 `<style scoped>`，全局色由 Element Plus 主题变量驱动；保持白底扁平风。

## 5. 配置与密钥

- `config/config.yaml` **永不入库**（已写入 `.gitignore`）。
- 第一次拉代码后，开发者从 `config/config.example.yaml` 复制一份并填入 `api_key`。
- 启动时 `config.py` 校验所有必填字段；缺失则进程退出并打印缺失字段名（不打印值）。
- 用户提示词 `prompt_*.json` 默认 gitignore，仅 `prompt_sample.json` 进库；如需共享提示词，通过 PR 单独添加并改名为 `prompt_sample_<topic>.json`。

## 6. 错误处理与日志

- 后端使用 `logging`（root logger），日志级别由 config 控制；默认 INFO。
- 上游 4xx/5xx：记录响应状态 + 摘要（前 200 字符），剥离 `Authorization` header。
- 任务失败统一写入 `tasks` 表的 `error_message` 字段，供前端展示。
- 前端错误：toast (Element Plus `ElMessage`) 提示；429 队列满显式给出"当前队列 X / 上限 Y"。

## 7. 测试期望

| 范围 | 内容 |
|------|------|
| 后端单元 | `task_manager`：队列上限拒绝、取消排队任务、并发数变更不丢任务；`storage`：CRUD 正确；`generator`：mock 上游 OK + 错误 + 取消三条路径 |
| 后端集成 | 启动 FastAPI TestClient，跑 POST /api/tasks → 队列 → 完成的全链路（mock 上游） |
| 前端 | 至少手动 smoke：三个页面都能进入、新建任务能发出请求、SSE 进度能动 |

测试位于 `backend/tests/`，命令 `pytest` 全绿是 PR 合并的硬门槛。

## 8. 本地运行

### 8.1 准备配置

Windows PowerShell 环境：

```powershell
Copy-Item config/config.example.yaml config/config.yaml
# 编辑 config/config.yaml，填入 api_key
```

macOS / Linux shell 环境：

```sh
cp config/config.example.yaml config/config.yaml
# 编辑 config/config.yaml，填入 api_key
```

### 8.2 启动后端

Windows PowerShell 环境：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

macOS / Linux shell 环境：

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 8.3 启动前端

```sh
cd frontend
npm install
npm run dev
# 默认 http://localhost:5173，已配置 /api -> http://127.0.0.1:8000 的 dev proxy
```

### 8.4 访问

浏览器打开 `http://localhost:5173`。新建任务即可看到生成的图片落到 `images/`。

## 9. Git 与提交

- 一个 lane = 一个/多个独立提交，提交信息形如：
  - `backend: scaffold task manager (B5)`
  - `frontend: implement TaskListView (F4)`
- 不允许跨 lane 提交。
- 不允许 `--no-verify`。

## 10. 恢复执行约定

`docs/todolist.md` 是断点续跑的唯一真相源。每个 Agent 的工作流：

1. 读 `docs/todolist.md`，定位本 lane 第一个未勾选项。
2. 完成后立即勾选并提交。
3. 全部完成后在文件末尾追加 `Lane completed by <agent> at <ISO 时间>`。

如果一个 Agent 中途崩溃，重启它只需要再传同一个 prompt——它会从未勾选项继续。

## 11. AI 助手限制

- 不要新建 `assets/` 之外的截图、二进制文件。
- 不要修改 `demo.py`（保留作历史参考）。
- 不要在代码里硬编码 API key 或上游 URL（一律走 config）。
- 不要假设其他 lane 的实现细节，只信任 `docs/interface.md` 与 `docs/prd.md`。

---

## 2026-05-08 Addendum — 模板 DB 化 + Task title 工程约定

> 本次迭代新增/调整的工程约定。前期 §1–§11 仍然有效；本节仅补充。
>
> 计划文件：`C:\Users\PC\.claude\plans\agent-skill-abundant-kernighan.md`。
> 需求详情：[prd.md §2026-05-08 Addendum](prd.md)。

### A.1 新增 / 调整目录

```
backend/app/
  scripts/
    __init__.py
    init_db.py            # 新增：CLI 入口 `python -m app.scripts.init_db`

frontend/src/
  views/
    PromptTemplatesView.vue  # 新增

prompt/                   # 保留作为种子，初始化后不再读写
```

### A.2 Lane 与所有权（本期）

| Lane | 新增可写 | 注意 |
|------|---------|------|
| **Backend** | `backend/app/scripts/**`（新建）、`backend/app/core/storage.py`（schema + 模板 CRUD 改 DB）、`backend/app/api/prompts.py`（PUT 端点）、`backend/app/schemas.py`、`backend/app/main.py`（lifespan 移除 `ensure_sample_prompt`）、`backend/app/core/task_manager.py` / `generator.py`（title 锁定 + 回填） | 不动 `prompt/*.json`（保留作为种子）；不在 lifespan 自动 init |
| **Frontend** | `frontend/src/views/PromptTemplatesView.vue`（新建）、`frontend/src/components/NewTaskDrawer.vue` / `AppSidebar.vue`、`frontend/src/router/index.ts`、`frontend/src/api/client.ts`、`frontend/src/types/api.ts` | 模板下拉调用方式不变（路径不变，后端切 DB 前端无感） |

### A.3 命名 / 编码约定

- 模板 id：小写下划线 slug；冲突自动后缀 `_2`、`_3`（沿用既有 `_make_unique_id`）。
- 任务 title：字符串 trim 后非空才算用户提供；空时由后端兜底 `prompt[:30]`；前端 maxlength=60。
- 不引入新依赖（前后端都是）。
- payload 字段命名走后端 snake_case：`save_as_template`、`template_name`、`title`。
- 不在日志中输出 prompt 全文（最多前 60 字符）。

### A.4 测试期望

| 范围 | 内容 |
|------|------|
| Backend 单元 | `prompt_templates` CRUD（含 sample 保护）、`init_prompt_templates_from_files` 幂等、`task_manager.submit` 的 title 兜底、POST /api/tasks 三种 title 路径（不传 / 传 / 仅空白）、save_as_template 落库 |
| Backend 集成 | 启动 → 调用 init script → 列模板返回种子条目 |
| Frontend | 手动 dev smoke：不填 title / 填 title / 勾选保存模板 / 模板配置页 CRUD 五条路径 |

### A.5 本期 contract 流程

本期 contract 直接落到 `docs/interface.md`（即 §3 / §10 增量），不走 `interface.draft.md`。Phase C 不需要合并步骤。

### A.6 AI 助手限制（本期）

- 不要删除 `prompt/*.json`（即使初始化已完成）。
- 不要在 lifespan 自动调用 init（这是用户明确要求的「手动调用」语义）。

---

## 2026-05-09 Addendum — 插件化迭代规章补充

> 本次迭代新增/调整的工程约定。前期 §1–§11 仍然有效;本节仅补充。

### A.1 新增 / 调整目录

```
backend/app/
  providers/
    __init__.py        # PROVIDER_REGISTRY = {"momo": MomoProvider()}
    base.py            # Protocol + dataclasses (CredField/ModelInfo/HttpCall/ParsedResult)
    momo.py            # MomoProvider 实现
  core/
    provider_store.py  # Protocol + SqliteProviderStore + InMemoryProviderStore
    secret_box.py      # AES-256-GCM at-rest 加密
  api/
    providers.py       # /api/providers/* 路由

frontend/src/
  views/
    ProvidersView.vue
  stores/
    useProviderStore.ts        # 替代旧 useApiAuthStore
  components/
    ProviderConfigDialog.vue
    AddKeyDialog.vue
    ProviderPicker.vue         # 三级联动: provider→key→model

data/
  master.key                   # 主密钥文件 (gitignored;normal 模式自动生成)
```

### A.2 Lane 与所有权 (本轮)

新增/调整的可写路径:

| Lane | 新增可写 | 注意 |
|------|---------|------|
| **Backend Agent** | `backend/app/providers/**`、`backend/app/core/provider_store.py`、`backend/app/core/secret_box.py`、`backend/app/api/providers.py`、`docs/interface.draft.md`(本轮 contract,Phase C 后由 orchestrator 合并到 `interface.md`)、`docker-compose.yml`、`backend/Dockerfile`(若需) | **不要直接改 `docs/interface.md`** — 只写 draft |
| **Frontend Agent** | `frontend/src/views/ProvidersView.vue`、`frontend/src/stores/useProviderStore.ts`、`frontend/src/components/ProviderConfigDialog.vue`、`frontend/src/components/AddKeyDialog.vue`、`frontend/src/components/ProviderPicker.vue` | 删除 `frontend/src/stores/useApiAuthStore.ts` 与 `frontend/src/components/ApiCredentialsDialog.vue` |

**绝不动**(两个 lane 共同):
- `docs/prd.md`、`docs/explanation.md` — 本轮已写完。
- `docs/interface.md` (持久化版) — 由 orchestrator 在 Phase C 合并;Backend lane 只写 `interface.draft.md`。
- `demo.py`(沿用约定 §11)。
- 对方 lane 的源码树。

### A.3 Provider 抽象约定

每个 Provider 必须实现 `Provider` Protocol(三个方法 + 元数据):

```python
class Provider(Protocol):
    id: str
    display_name: str
    credential_fields: list[CredField]
    default_base_url: str

    def list_models(self, creds: dict, base_url: str, timeout: int) -> list[ModelInfo]: ...
    def build_request(self, task: GeneratorTask, creds: dict, base_url: str, model: str) -> HttpCall: ...
    def parse_response(self, resp: requests.Response) -> ParsedResult: ...
```

- `base_url` 存 **origin**(如 `https://momoapi.top/v1`),具体 endpoint path 由 Provider 内部决定。
- `list_models` 必须在 `add_key` 流程中可被同步调用(无副作用、阻塞返回);失败抛 `UpstreamError`。
- 不允许 Provider 实现内部读取全局 config 或环境变量 — 所有依赖通过参数注入。

### A.4 凭据生命周期

| 阶段 | 路径 |
|------|------|
| 浏览器输入 | `AddKeyDialog.vue` 表单 |
| 传输加密 | `crypto.ts` RSA-OAEP `encryptObject(obj)` 逐字段加密 |
| 后端解密 | `crypto.py` `decrypt_dict(payload)` |
| 持久化 (`normal`) | `secret_box.py` AES-GCM(独立 nonce)→ `provider_keys.encrypted_credentials` BLOB |
| 持久化 (`demo`) | `InMemoryProviderStore` dict (进程内) |
| 调用上游 | 从 store 取出 → 解密 → 用完即弃,绝不进 logger / response / error_message |

### A.5 三层 config loader 实现规则

- 单一入口:`backend/app/config.py::get_config()`(沿用)
- 加载顺序:yaml → 应用 env 覆盖 → Pydantic 校验
- env 命名规则见 PRD §A.2.5;`secret_key` 是顶层特判
- CSV 类字段(`server.cors_origins`)从 env 读取时按 `,` 分隔
- 实现拆为纯函数 `apply_env_overrides(yaml_dict: dict, env: Mapping[str,str]) -> dict`,带单测覆盖嵌套、CSV、缺失三种情况

### A.6 测试期望 (本轮新增)

| 范围 | 内容 |
|------|------|
| `test_config_layers.py` | yaml + env 覆盖、嵌套、CSV、`VIBE_SECRET_KEY` 顶层特判 |
| `test_providers.py` | `MomoProvider.list_models` (mock requests 200/4xx/timeout)、`build_request` body 形态、`parse_response` 三路径 |
| `test_secret_box.py` | encrypt/decrypt round-trip;`VIBE_SECRET_KEY` 优先级;主密钥文件自动生成 |
| `test_provider_store.py` | Sqlite + InMemory 双实现 CRUD 一致;凭据加解密 round-trip;级联删 Key/Models |
| `test_providers_api.py` | TestClient 全套路由 happy/sad path |
| `test_tasks_with_provider.py` | 任务路由按 `provider_id`/`key_id` 解析,失败回写 `error_message` |

### A.7 本轮 contract 流程

1. Backend lane 在 B 序列中段写 `docs/interface.draft.md` (新增/改动端点 + schemas)。
2. Backend lane 显式勾选其 contract 行 → orchestrator 检测 gate(文件存在 + > 500 字节 + 行勾选)→ 启动 Frontend lane。
3. Frontend lane 读 `docs/interface.draft.md`(本轮唯一 contract 真相源,与 `docs/interface.md` 已有内容并存)。
4. Phase C 由 orchestrator 把 `interface.draft.md` 合并入 `interface.md`,冲突端点用 `[已弃用 / DEPRECATED at 2026-05-09]` 与 `[v2 — 自 2026-05-09]` 双留。

### A.8 失败原因展示约定

- 后端 `error_message` 必须脱敏(不含 Authorization,response body 截断 200 字符)。
- 前端 `TaskCard.vue` / `HistoryView.vue` 在 `failed` 状态下可见,设计:13px 红色单行 + tooltip + 复制按钮。
- 文案中"(legacy)"标识专留给 `provider_id`/`key_id` 为 NULL 的旧任务。

### A.9 Docker / 部署

- `docker-compose.yml` 增 `environment:` 区段示例(注释列出全部 `VIBE_*` 可调项);`VIBE_MODE: normal` 显式默认。
- `data/master.key` 加入 `.gitignore` 子项(若 `data/` 已整体忽略可不加)。README 强调备份。
- demo 模式启动示例:`docker compose run -e VIBE_MODE=demo backend ...` 或本地 `VIBE_MODE=demo uvicorn ...`。

---

## 2026-05-09 Addendum (II) — img2img 工程约定

> 本次迭代新增/调整的工程约定。前期 §1–§11 与上一轮 Addendum 仍然有效；本节仅补充。
>
> 计划文件：`C:\Users\PC\.claude\plans\images-temp-provider-prompt-momo-resume-sleepy-squid.md`。
> 需求详情：[prd.md §2026-05-09 Addendum (II)](prd.md)。

### B.1 新增 / 调整目录

```
backend/app/
  api/
    uploads.py            # POST /api/uploads/temp（multipart 接收）

frontend/src/
  components/
    NewTaskDrawer.vue     # 改：加参考图多选上传 / 预览 / 移除
    TaskCard.vue          # 改：加输入图缩略图（input_image_urls 存在时）

images/                   # local storage 静态目录
  temp/                   # local 模式参考图目录；OSS 模式写入 <prefix>temp/<sha1>.<ext>
```

无新增前端 store / view。Provider 抽象的扩展不开新文件，落在既有 `providers/base.py` 与 `providers/momo.py`。

### B.2 Lane 与所有权（本轮）

新增/调整的可写路径（在前两轮所有权基础上）：

| Lane | 新增可写 | 注意 |
|------|---------|------|
| **Backend Agent** | `backend/app/api/uploads.py`（新建）、`backend/app/providers/base.py`（扩 Protocol）、`backend/app/providers/momo.py`（实现 img2img 入口）、`backend/app/core/generator.py`、`backend/app/core/task_manager.py`、`backend/app/core/storage.py`（迁移加列）、`backend/app/api/tasks.py`、`backend/app/api/providers.py`、`backend/app/schemas.py`、`backend/app/config.py`、`backend/app/errors.py`、`backend/app/main.py`、`config/config.example.yaml`、`docs/interface.draft.md`（**本轮 contract，Phase C 后由 orchestrator 合并到 `interface.md`**）、`docs/todolist.md`（仅本轮 B 行） | 上一轮的 `docs/interface.draft.md` 已被合并删除，本轮重新创建；**不要直接改 `docs/interface.md`** |
| **Frontend Agent** | `frontend/src/components/NewTaskDrawer.vue`、`frontend/src/components/TaskCard.vue`、`frontend/src/views/HistoryView.vue`、`frontend/src/api/client.ts`、`frontend/src/types/api.ts`、`frontend/src/stores/useProviderStore.ts`、`docs/todolist.md`（仅本轮 F 行） | 不动 backend / docs 持久化文件 |

**绝不动**（两个 lane 共同）：
- `docs/prd.md`、`docs/explanation.md` —— 本轮已写完。
- `docs/interface.md`（持久化版）—— Phase C 由 orchestrator 合并。
- 上一轮已稳定的 `providers.py` 路由、`secret_box.py`、`provider_store.py`：仅按需做最小扩展（如 ProviderSummary 多一个字段），不重构。
- `demo.py`（沿用约定 §11）。
- 对方 lane 的源码树。

### B.3 Provider 协议扩展约定

- Provider 元数据新增类属性 `supports_image_input: bool`（默认 `False`，在 Protocol 中显式声明）。
- 选择性方法 `build_image_edit_request(task, creds, base_url, model) -> HttpCall`：未实现的 Provider，`generator.py` 在 dispatch 前先 `getattr(provider, "supports_image_input", False)` 探测，为 `False` 则抛 `ProviderCapabilityError("image input not supported")` —— 此异常映射到 `400 provider_capability_unsupported`。
- 已实现的 Provider 的 `build_image_edit_request` 可能返回带 `files` 字段的 `HttpCall`（multipart）；`generator.py` dispatch 时按 `files` 是否非空二选一走 multipart 或 JSON。
- `parse_response` 复用既有实现，不做分支。

### B.4 `HttpCall` 扩展

`HttpCall` dataclass 新增两字段：

```python
@dataclass
class HttpCall:
    url: str
    method: str
    headers: dict[str, str] = field(default_factory=dict)
    json_body: Optional[dict] = None
    files: Optional[dict[str, tuple[str, bytes, str]] | list[tuple[str, tuple[str, bytes, str]]]] = None
    data: Optional[dict[str, str]] = None                       # multipart 普通字段
```

约束：
- `files` 与 `json_body` 互斥；调用方有责任只填一个。
- multipart 时**禁止** Header 里手填 `Content-Type: application/json`，`requests` 会自动生成 `multipart/form-data; boundary=...`。

### B.5 上传与存储约定

- local 模式 `images_dir/temp/` 在启动时确保存在；OSS 模式不依赖本地缓存路径。
- 上传 storage key：`temp/<sha1(content)>.<ext>`，扩展名按 sniff 结果（不信用户传的 ext）。
- 同内容文件不重复保存（去重），由 active `StorageBackend.exists/save/url` 决定 local 或 OSS 分支。
- 任务表 `tasks` 保留 `input_image_path TEXT NULL` 兼容旧单图字段，并新增 `input_image_paths TEXT NULL`（JSON 数组，探测式 ALTER，幂等）。启动迁移会把旧 `input_image_path` 回填为 `["..."]`。
- 上传文件**不**在任务结束时清理；保留以便 TaskCard 历史回看。GC 留作下一工单。

### B.6 配置增量

`config.example.yaml` 与 env 覆盖表新增：

| yaml 路径 | env 变量 | 默认值 |
|---|---|---|
| `defaults.max_upload_bytes` | `VIBE_DEFAULTS_MAX_UPLOAD_BYTES` | `10485760`（10 MiB）|

### B.7 测试期望（本轮新增）

| 范围 | 内容 |
|------|------|
| `test_providers.py`（既有，新增用例） | momo `build_image_edit_request` 返回 `HttpCall` 形态正确（method=POST，url 末段 `/images/edits`，files 字段含 image，data 字段含 model/prompt/size）；`supports_image_input == True` |
| `test_uploads.py`（新增） | 上传 PNG 200；非图片 400；超大 413；同内容上传两次返回相同 `input_image_path`；temp 目录被创建 |
| `test_generator.py`（既有，新增用例） | img2img 分支 mock multipart `requests.post`；`ReferenceImage` 由 storage-backed bytes/URL 构成；不支持 provider 抛 `ProviderCapabilityError` |
| `test_storage_providers_migration.py`（既有，新增用例） | 旧 db 启动后 `tasks` 表多出 `input_image_path` / `input_image_paths` 列；旧单图字段回填为 JSON 数组；幂等 |
| `test_tasks_with_provider.py`（既有，新增用例） | 旧 `input_image_path` 与新 `input_image_paths` 都可走 img2img；冲突返回 `input_image_conflict`；`provider_capability_unsupported` 错误码触发 |
| `test_providers_api.py`（既有，新增用例） | `GET /api/providers` 响应含 `supports_image_input: true`（momo） |

### B.8 本轮 contract 流程

1. Backend lane 在 B 序列中段（推荐 B6）写 `docs/interface.draft.md`：列出 `POST /api/uploads/temp`、`POST /api/tasks` 参考图字段、`ProviderSummary.supports_image_input`、`TaskItem.input_image_paths / input_image_urls` 及旧字段兼容、新错误码。
2. Backend lane 显式勾选其 contract 行 → orchestrator 检测 gate（文件存在 + > 500 字节 + 行勾选）→ 启动 Frontend lane。
3. Frontend lane 读 `docs/interface.draft.md`（本轮唯一 contract 真相源，与 `docs/interface.md` 已有内容并存）。
4. Phase C 由 orchestrator 把 `interface.draft.md` 合并入 `interface.md`，新端点附 `[v2 — 自 2026-05-09]` 等版本标记；不冲突的 `TaskItem` 字段扩展直接补到既有 §10.5 类型定义里。

### B.9 安全 / 边界

- 参考图 key 必须以 `temp/` 开头，不能是绝对路径，不能包含 `..` 或反斜杠，并且必须通过 active `StorageBackend.exists(key)`；否则 `400 input_image_not_found`。
- 上传文件落盘前用 Pillow / `imghdr` 的头校验过一次；MIME 不可信。
- 错误信息中**不**回显完整文件名给前端（仅返回 sha1 短哈希），避免暴露文件系统细节。
- 上传接口暂不做速率限制（本期单机工具，留作下个工单）。

---

## 2026-05-10 Addendum — Demo Token 鉴权工程约定

> 本次迭代新增工程约定。前期所有 §1–§11 与前几轮 Addendum 仍然有效；本节仅补充。
> 需求详情：[prd.md §2026-05-10 Addendum](prd.md)。

### C.1 新增 / 调整目录

```
backend/app/
  main.py                  # 改：+DemoAuthMiddleware, +_init_demo_token
backend/tests/
  test_demo_auth.py        # 新增：middleware 单测

frontend/src/
  composables/
    useDemoGuard.ts        # 新增：isDemoDenied ref + token 工具函数
  api/
    client.ts              # 改：+demoHeaders(), +getHealth(), demo_required 处理
  composables/
    useTaskStream.ts       # 改：SSE URL 带 ?demo_token
  App.vue                  # 改：挂载时读 URL token + health check + 遮罩

data/
  demo_token.txt           # 自动生成（gitignored）
```

### C.2 Lane 与所有权（本轮）

| Lane | 新增可写 | 注意 |
|------|---------|------|
| **Backend Agent** | `backend/app/main.py`（已部分改）、`backend/tests/test_demo_auth.py`（新建）、`docs/interface.draft.md`（**本轮 contract gate**） | 不动 `frontend/**` |
| **Frontend Agent** | `frontend/src/composables/useDemoGuard.ts`（已建）、`frontend/src/api/client.ts`（已部分改）、`frontend/src/composables/useTaskStream.ts`、`frontend/src/App.vue` | 不动 `backend/**`、`docs/interface.md` |

**已完成项（本轮启动前已做）：**
- 后端：`main.py` 已加 `_init_demo_token` + `DemoAuthMiddleware` + 注册中间件；`config.example.yaml` 已加说明注释。
- 前端：`useDemoGuard.ts` 已创建；`client.ts` 已加 `demoHeaders()` 并注入到 `request<T>`。

### C.3 Token 规则

- Token 字符集：`secrets.token_urlsafe(32)`（URL-safe base64，43 字符）。
- 持久化路径：`config.database_path.parent / "demo_token.txt"`（与 db 同目录）。
- 固定方式：`config.yaml` 中 `secret_key: "your-token"` 即可覆盖自动生成。
- `data/demo_token.txt` 必须在 `.gitignore` 中（检查一下）。

### C.4 前端安全边界

- Token 只存 `localStorage`，不写 cookie，不进任何日志 / 响应体。
- `isDemoDenied.value = true` 后，遮罩必须覆盖整个 viewport，包括 `<AppSidebar>` 和 `<RouterView>`，不可绕过。
- `getHealth()` 是唯一的"前置检查"调用；其他 API 失败时也可触发 `isDemoDenied` 以防漏网。

### C.5 测试期望（本轮新增）

| 范围 | 内容 |
|------|------|
| `test_demo_auth.py` | normal 模式不拦截；demo 模式无 token 返回 401 `demo_required`；header 正确返回 200；query param 正确返回 200；OPTIONS 放行；非 /api/ 路径放行 |
| Frontend | `npm run build` 类型通过；手动 smoke：带 token URL → 正常使用；无 token → 遮罩展示 |

### C.6 本轮 contract 流程

1. Backend lane 完成 `main.py` 改动的测试 + 写 `docs/interface.draft.md`（包含 `401 demo_required` 响应 schema、`X-Demo-Token` header 说明、`?demo_token` query param 说明）。
2. Backend lane 勾选 contract 行 → orchestrator 检测 gate → 启动 Frontend lane。
3. Frontend lane 读 `docs/interface.draft.md`。
4. Phase C 由 orchestrator 合并 draft 入 `interface.md`。


## 2026-05-11 Addendum — Storage backend abstraction

> 本节由 `docs/explanation.draft.md` 于 Phase C 合并而来。原计划同时存在的临时 lane（Storage Core / Storage Providers）已经完成；以下规则在未来涉及 storage 抽象层的工作时仍然有效。

### D.1 本轮 Lane 划分与所有权

本轮新增两个 Lane（Backend 内部进一步拆分），与历史 Backend/Frontend 命名区分开：

| Lane | 可写路径 | 不可写路径 |
|------|---------|-----------|
| **Storage Core Agent**（Upstream） | `backend/app/core/storage_backend.py`（新建）、`backend/app/core/storage_backends/__init__.py`（新建空骨架）、`backend/app/config.py`、`backend/app/config_layers.py`、`backend/app/main.py`、`backend/app/core/generator.py`、`backend/app/core/task_manager.py`、`backend/app/api/uploads.py`、`backend/app/api/history.py`、`backend/app/api/tasks.py`、`backend/tests/test_storage_local.py` 等 Lane 自测、`config/config.example.yaml`（**仅追加 storage 段示例**）、`docs/storage-backend-contract.md`（新建，本轮契约）、`docs/todolist.md`（仅本轮 S 行） | `frontend/**`、`backend/app/core/storage_backends/{aliyun,tencent,aws_like}.py`、`backend/app/scripts/migrate_to_oss.py`、`backend/requirements.txt`、`docs/prd.md`、`docs/explanation.md`、`docs/interface.md`、`docs/todolist.md`（除 S 行外） |
| **Storage Providers Agent**（Downstream） | `backend/app/core/storage_backends/aliyun.py`、`backend/app/core/storage_backends/tencent.py`、`backend/app/core/storage_backends/aws_like.py`（新建 3 个适配器，AWS / Cloudflare R2 / MinIO 共用 aws_like）、`backend/app/scripts/migrate_to_oss.py`（新建）、`backend/requirements.txt`（**仅追加**新 SDK 行）、`backend/tests/test_storage_aliyun.py` / `test_storage_tencent.py` / `test_storage_aws_like.py` 等 Lane 自测、`config/config.example.yaml`（**仅完善**每家具体字段示例与注释，不动 storage 顶层结构）、`docs/todolist.md`（仅本轮 P 行） | `frontend/**`、Storage Core Agent 的所有可写路径、`docs/prd.md`、`docs/explanation.md`、`docs/interface.md`、`docs/storage-backend-contract.md`（只读契约） |

跨 Lane 修改一律走"上报 → 主对话决定 → 必要时再发一个小 agent run"，不允许互相 monkey-patch。本轮真实运行中触发了一次该流程：Storage Core 报出 `backend/app/schemas.py:TaskItem` 的 `image_url` / `input_image_url` 用 `@computed_field` 硬编码 `/images/` 前缀，跨过了 storage 抽象层；schemas.py 不在任一 lane 的写权限内，主对话以 follow-up 补丁修复（改为普通字段 + 在 `api/tasks.py` / `api/history.py` 中调 `hydrate_task_item_urls()`）。2026-05-11 多参考图升级后，`input_image_urls` 同样由该 hydrate 层通过 active storage backend 派生。

### D.2 命名约定

| 实体 | 规则 | 示例 |
|------|------|------|
| 存储 key（生成图）| `generated_{task_id}.{ext}` | `generated_4c2b1e8a-....jpeg` |
| 存储 key（临时图）| `temp/{sha1}.{ext}` | `temp/0fc1...png` |
| 适配器类名 | `<Provider>Backend` PascalCase | `AliyunOSSBackend`、`AwsLikeBackend` |
| 配置子模型 | `<Provider>StorageConfig` | `AliyunStorageConfig`、`TencentStorageConfig` |
| Env 变量 | `VIBE_STORAGE_<PROVIDER>_<KEY>` | `VIBE_STORAGE_ALIYUN_BUCKET` |
| 异常 | `StorageError(provider: str, op: str, key: str | None, cause: Exception)` | — |

`prefix` 由适配器内部拼到 `key` 前；调用方传入的 `key` **不含** prefix。

### D.3 测试约定

- 每家适配器单测**禁止真连云**：用 `unittest.mock` 替换 SDK client，或使用 `moto`（仅对 boto3）/ `responses`；test 文件用 `pytest.importorskip` 守护 SDK 缺失，未装 SDK 时自动 skip 而非 fail。
- 本地集成测试只覆盖 `LocalBackend` 与 MinIO（开发机起一个 Docker MinIO 即可），且必须放在 `backend/tests/integration/` 目录，由 `pytest -m integration` 显式运行；默认 `pytest` 跳过。

### D.4 启动顺序

`backend/app/main.py` 的 `_lifespan` 现已构造 Storage / TaskManager / CryptoManager / ProviderStore。本轮在 Storage 之前插入 `storage_backend = build_storage_backend(config.storage, images_dir=config.images_dir)`，挂到 `app.state.storage_backend`。Generator / TaskManager / uploads / history / tasks 通过 `request.app.state.storage_backend` 或显式注入访问。

### D.5 跑测命令（本轮）

- `cd backend && pytest -q`：所有单测（含本轮新增本地后端 + 各家适配器 mock 测试，未装 SDK 时 skip）。
- 装 SDK 后（`pip install boto3 oss2 cos-python-sdk-v5`）跑同一命令即覆盖三家适配器 mock 测试。
- `cd backend && python -m app.scripts.migrate_to_oss --dry-run`：迁移脚本干跑（要求 `storage.backend != local`）。
