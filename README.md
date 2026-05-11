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

```powershell｜sh
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

### 迁移本地图片到对象存储

当 `config.yaml` 的 `storage.backend` 从 `local` 切到 `aliyun` / `tencent` / `cloudflare` / `aws` / `minio` 后，历史本地图片不会自动跟过去；用以下脚本一次性迁移：

```sh
cd backend
python -m app.scripts.migrate_to_oss --dry-run            # 干跑，只列出待迁移条目
python -m app.scripts.migrate_to_oss                      # 实际上传并更新 DB 中的 image_path
python -m app.scripts.migrate_to_oss --limit 50           # 仅迁移前 50 条（分批跑）
```

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

### SSL 证书配置

如果您已放入真实的正式证书（放置在 `./docker/certs/` 目录），请在 `docker-compose.yml` 中移除或注释掉前端服务的自动生成脚本映射：`- ./docker/generate-ssl.sh:/docker-entrypoint.d/generate-ssl.sh:ro`。如果证书文件名不是 `cert.pem` 和 `key.pem`，请相应修改 `./docker/nginx.conf` 中的 `ssl_certificate` 和 `ssl_certificate_key` 路径。

### 启动

```sh
docker compose up -d --build
```

### Demo 模式启动

```powershell
$env:VIBE_MODE="demo"; docker compose up -d --build
```

```sh
VIBE_MODE=demo docker compose up -d --build
```

获取 demo 访问邀请链接：

```powershell
$token = docker compose logs backend | Select-String 'Demo mode' | ForEach-Object { $_ -replace '.*access token: ', '' }
Write-Host "http://localhost:8080/?demo_token=$token"
```

```sh
echo "http://localhost:8080/?demo_token=$(docker compose logs backend | grep 'Demo mode' | sed 's/.*access token: //')"
```

```powershell｜sh
docker compose logs -f backend     # 日志
docker compose down                # 停止
docker compose up -d --build       # 重建
```

### 迁移本地图片到对象存储（容器内）

切换 `storage.backend` 后，在运行中的 backend 容器里执行迁移脚本：

```sh
docker compose exec backend python -m app.scripts.migrate_to_oss --dry-run    # 干跑
docker compose exec backend python -m app.scripts.migrate_to_oss              # 实际迁移
docker compose exec backend python -m app.scripts.migrate_to_oss --limit 50   # 分批
```
