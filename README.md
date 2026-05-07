# vibe-image

本地浏览器 UI + Python 后端，把 `demo.py` 中的单次提示词生图扩展为可长期运行的服务：提示词资产化、并发可调、队列限流、历史记录与图片绑定。

参考文档：
- 产品需求：`docs/prd.md`
- 工程规章：`docs/explanation.md`
- 接口契约：`docs/interface.md`
- 进度看板：`docs/todolist.md`

## Backend

### 准备配置

复制配置模板并填入真实 api_key：

```powershell
Copy-Item config/config.example.yaml config/config.yaml
# 编辑 config/config.yaml，把 api.api_key 改成真实 key
```

`config/config.yaml` 已被 `.gitignore` 排除，绝不会被提交。

### 启动后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动成功后：
- OpenAPI 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

### 运行测试

```powershell
cd backend
pytest -q
```

测试不会发起任何真实网络请求（HTTP 调用全部被 mock）。

### 关键路径

- 任务持久化在 `data/vibe.db`（SQLite，由 `.gitignore` 排除）。
- 生成的图片落到 `images/generated_<task_id>.<ext>`。
- 提示词模板是 `prompt/prompt_<id>.json`；只有 `prompt_sample.json` 入库。

## Frontend

Vue 3 + Vite + TypeScript + Element Plus + Pinia + Vue Router 单页应用。

### 前置

- Node.js 18+ 和 npm。
- 后端必须先运行在 `http://127.0.0.1:8000`（见上文）。Vite dev server 通过代理把 `/api` 与 `/images` 转发到后端。

### 启动开发模式

```powershell
cd frontend
npm install
npm run dev
```

默认打开 <http://localhost:5173>。三个页面：
- `/` — 任务列表（实时 SSE 推送进度）
- `/history` — 历史记录（搜索 / 筛选 / 分页 / 重新生成）
- 侧边栏右下角的"设置"按钮 — 调整并发数与队列上限

### 构建生产包

```powershell
cd frontend
npm run build
```

构建命令会先跑 `vue-tsc --noEmit` 做类型检查再产出 `dist/`，这是 PR 合并前的硬门槛。
