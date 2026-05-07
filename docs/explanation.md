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
