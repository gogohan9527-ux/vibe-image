# vibe-image

本地浏览器 UI + Python 后端，提示词生图服务：提示词资产化、并发可调、队列限流、历史记录与图片绑定。

参考文档：
- 产品需求：`docs/prd.md`
- 工程规章：`docs/explanation.md`
- 接口契约：`docs/interface.md`
- 进度看板：`docs/todolist.md`

## Backend

### 准备配置

```sh
cp config/config.example.yaml config/config.yaml
```

### 启动后端

#### 首次启动

```sh
cd backend
python -m app.scripts.init_db
```

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

启动成功后：
- OpenAPI 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

### 运行测试

```sh
cd backend
pytest -q
```

测试不会发起任何真实网络请求（HTTP 调用全部被 mock）。

### 关键路径

- 任务持久化在 `data/vibe.db`（SQLite，由 `.gitignore` 排除）。
- 生成的图片落到 `images/generated_<task_id>.<ext>`。
- 提示词模板种子文件在 `prompt/prompt_*.json`，通过 `init_db` 脚本导入 SQLite。

## Frontend

Vue 3 + Vite + TypeScript + Element Plus + Pinia + Vue Router 应用。

### 前置

- Node.js 18+ 和 npm。
- 后端必须先运行在 `http://127.0.0.1:8000`（见上文）。Vite dev server 通过代理把 `/api` 与 `/images` 转发到后端。

### 启动开发模式

```sh
cd frontend
npm install
npm run dev
```

### 构建生产包

```sh
cd frontend
npm run build
```

---

## Docker Compose 部署

### 准备配置 (可选)

```sh 
cp config/config.example.yaml config/config.yaml
cp .env.example .env
```

### 启动

```sh
docker compose up -d --build
```

### Demo 模式启动

```sh
VIBE_MODE=demo docker compose up -d --build           # Linux / macOS / WSL
```

```powershell
$env:VIBE_MODE="demo"; docker compose up -d --build   # Windows PowerShell
```

```sh
docker compose logs -f backend     # 日志
docker compose down                # 停止
docker compose up -d --build       # 重建
```
