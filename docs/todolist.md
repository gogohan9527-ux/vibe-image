# vibe-image — 执行进度追踪 (TodoList)

> **断点续跑约定**：每个 Agent 启动后第一步是读本文件，定位本 lane（B 行 = Backend、F 行 = Frontend）第一个 `[ ]` 未勾项继续执行；完成后立刻把方括号改为 `[x]` 并提交。整个文件只允许 Agent 修改自己 lane 下的勾选状态与对应的"备注"列。其余文档（PRD、explanation、interface）按 [explanation.md §2](explanation.md) 的所有权约束。
>
> **Phase A**（需求文档）已在主对话中完成；下方 B / F 两个 lane 属于 **Phase B**，需用户下达"恢复执行 / resume"指令后由两个 subagent 接管。

---

## Phase A — 需求与规章 (主对话已完成)

- [x] A1. 制定计划文件 `C:\Users\PC\.claude\plans\demo-vibe-image-ui-functional-wave.md`
- [x] A2. 写 `docs/prd.md`
- [x] A3. 写 `docs/explanation.md`
- [x] A4. 写 `docs/todolist.md`（本文件）
- [ ] A5. 用户下达 "resume / 恢复执行" 指令 → 进入 Phase B

---

## Phase B — Backend Agent
**所有权**：`backend/**`、`config/**`、`prompt/prompt_sample.json`、`docs/interface.md`、`.gitignore`、`README.md`（后端段落）。
**绝不动**：`frontend/**`、`docs/prd.md`、`docs/explanation.md`、`assets/**`。

| 序号 | 任务 | 验收点 | 状态 | 备注 |
|------|------|--------|------|------|
| B1 | 仓库脚手架：建 `backend/app/`、`backend/tests/`、`backend/requirements.txt`、`config/`、`prompt/`、`images/`、`data/`、`.gitignore` | 目录树与 explanation §1 一致；`.gitignore` 覆盖 `config.yaml` / `data/*.db` / `images/*` / `prompt/prompt_*.json`（保留 sample） | [x] | 目录与 .gitignore 全部就绪 |
| B2 | `app/config.py` + `config/config.example.yaml`：YAML 加载 + Pydantic 校验 | 缺字段时 `python -c "from app.config import get_config; get_config()"` 直接报错并打印缺失字段名 | [x] | Pydantic v2 BaseModel + lru_cache get_config |
| B3 | `app/core/storage.py` + SQLite schema：`tasks(id, prompt_id, prompt_text, model, size, quality, status, progress, image_path, error_message, created_at, started_at, finished_at)`、`prompts` 由文件系统兜底（不入库） | 单元测试覆盖 insert / list / get / update_progress / delete | [x] | 单连接 + RLock；prompts 走 JSON 文件 |
| B4 | `app/core/generator.py`：从 `demo.py` 抽取 API 调用 + 下载逻辑，参数化（prompt/size/quality/format），暴露 `progress_callback(stage: int)` 与 `cancel_event: threading.Event` | mock `requests.post` / `requests.get` 跑通 succeeded、failed、cancelled 三条路径 | [x] | 进度 10/50/80/100；脱敏日志 |
| B5 | `app/core/task_manager.py`：`ThreadPoolExecutor` + 显式 `pending` 队列 + `running_count`，提交时 `pending+running >= cap` 抛 `QueueFullError`；支持 `cancel(task_id)`、`set_concurrency(n)`、`set_queue_cap(n)` | 单元测试覆盖：满队拒绝、取消排队任务、取消运行中任务、并发降级不丢现有任务 | [x] | 显式 pending deque + 监听器 SSE 桥接 |
| B6 | FastAPI 路由：`api/tasks.py`（POST/GET/DELETE/GET by id）、`api/prompts.py`（GET/POST/DELETE，文件系统直读直写 `/prompt`）、`api/settings.py`（GET/PUT），`api/history.py`（GET 分页 + 过滤） | TestClient 跑通每条路由的 happy / sad path | [x] | 全部 12 条业务路由 + health |
| B7 | `api/tasks.py` 的 `GET /api/tasks/stream`（SSE）：监听任务状态变更并推送 `{task_id, status, progress, image_path?}` | 浏览器 `EventSource` 能收到至少 3 条事件（queued → running → succeeded） | [x] | 路径为 `/api/tasks/stream/events`（避开 `{task_id}` 冲突） |
| B8 | 全局异常处理 + CORS（来源由 config 驱动）+ 启动时建表 + 创建 `prompt/prompt_sample.json` | `uvicorn app.main:app` 启动无报错，`/docs` 可见 | [x] | VibeError 全局 handler；lifespan 建表 |
| B9 | 写 `docs/interface.md`（路由、请求体、响应体、错误码、SSE 事件 schema）；这是 Frontend Agent 的契约 | 文件存在且包含每个端点的 curl 示例 | [x] | 13 个端点全覆盖 |
| B10 | `backend/tests/` 至少覆盖：队列上限、取消排队、取消运行中、并发数变更、配置缺失退出 | `cd backend && pytest` 全绿 | [x] | 19 个用例全绿，约 2s |
| B11 | `README.md` 追加"后端运行"段（按 explanation §8.1–8.2） | 段落存在且命令可执行 | [x] | 新建 README.md；+ /images static mount, +1 test；+ DELETE /api/history/{id}, +4 tests; quality exposed in CreateTaskRequest |
| B12 | Backend lane 完工签名：在本文件末尾追加 `Backend lane completed at <ISO 时间>` | — | [x] | 见文末签名 |

---

## Phase B — Frontend Agent
**所有权**：`frontend/**`、`README.md`（前端段落）。
**绝不动**：`backend/**`、`config/**`、`prompt/**`、`docs/interface.md`（只读引用）、`docs/prd.md`、`docs/explanation.md`、`assets/**`（只读引用）。
**前置**：B9 完成后 `docs/interface.md` 即可读；F2 之前应等 B9 通过。其它 F 项可与 backend 并行。

| 序号 | 任务 | 验收点 | 状态 | 备注 |
|------|------|--------|------|------|
| F1 | 用 Vite 创建 `frontend/`：Vue 3 + TS + Element Plus + Pinia + Vue Router；配置 dev proxy `/api → http://127.0.0.1:8000`；统一中文 locale | `npm install && npm run dev` 起得来，根路径渲染空白布局 | [x] | 手写 package/tsconfig/vite.config，dev server OK |
| F2 | `src/api/client.ts`：基于 `docs/interface.md` 的强类型客户端（fetch 包装 + 错误归一化）；`src/types/api.ts` 定义所有请求 / 响应类型 | 任意一个端点能在 `npm run dev` 控制台手动调通 | [x] | ApiError 携带 ErrorBody；13 个端点全覆盖 |
| F3 | `src/components/AppSidebar.vue` + 路由 shell：左侧栏（品牌、新建任务按钮、任务列表 / 历史记录、设置图标），右侧 `<RouterView/>`，扁平白底，紧贴 `assets/page-task.png` | 三个路由可切换；视觉与截图近似 | [x] | 232px 侧栏 + 蓝色 active 高亮 |
| F4 | `src/views/TaskListView.vue` + `src/components/TaskCard.vue`：列表渲染、进度条、状态标签、缩略图、暂停/删除按钮 | 紧贴 `assets/page-task.png`；删除调用 `DELETE /api/tasks/{id}` 后从列表移除 | [x] | ETA 用 store 滚动平均；cancelling 态保留卡片 |
| F5 | `src/components/NewTaskDrawer.vue`：抽屉表单（提示词、选模板、模型、比例、尺寸、数量、保存为模板、优先），提交调用 `POST /api/tasks` | 紧贴 `assets/page-task-new.png`；429 错误显示队列上限提示并保留输入 | [x] | 比例联动尺寸；保存模板自动生成名；+ 质量 select (low/medium/high/auto, 默认 low) |
| F6 | `src/views/HistoryView.vue`：表格 + 搜索 + 状态筛选 + 分页 + 下载/删除/重新生成 | 紧贴 `assets/page-history.png`；重新生成会出现在 TaskListView | [x] | 后端无 history-delete 端点，按契约不展示该按钮；+ 删除按钮 (DELETE /api/history/{id}) |
| F7 | `src/components/SettingsDialog.vue`：并发与队列两个 NumberInput，调 `PUT /api/settings` 即时生效 | 修改后再下发任务时新并发立即生效 | [x] | 400 out_of_range 把 field 错误回填到对应输入 |
| F8 | `src/stores/useTaskStore.ts` + `src/composables/useTaskStream.ts`：单例 EventSource → `/api/tasks/stream`，状态变更推送到 Pinia | 任务卡进度条不刷新页面就动 | [x] | 单例 EventSource，progress 不回退；failed 不覆盖 progress |
| F9 | 三个页面对照 `assets/page-task.png`、`page-task-new.png`、`page-history.png` 做视觉走查；记录差异 | 走查清单存到本备注列 | [x] | 任务列表：4 列卡（图标/正文/缩略图/侧栏 ETA+按钮）已对齐；历史：表头"全部状态"下拉 + 操作列下载/重新生成已对齐；新建抽屉：1.提示词 / 选模板 / 2.模型 / 3.比例+尺寸 / 4.数量+优先 / 保存模板，与截图分组顺序一致；细节差异：背景色与字号取 Element Plus 默认（和截图差几像素） |
| F10 | `README.md` 追加"前端运行"段（按 explanation §8.3–8.4） | 段落存在且命令可执行 | [x] | 追加 ## Frontend 段（前置/dev/build） |
| F11 | Frontend lane 完工签名：在本文件末尾追加 `Frontend lane completed at <ISO 时间>` | — | [x] | 见文末签名 |

---

## 完工签名

<!-- Agent 在自己 lane 全部 [x] 后，在此处追加一行 -->
Backend lane completed at 2026-05-07T17:00:00 (revised: +static images)
Frontend lane completed at 2026-05-07T18:30:00
