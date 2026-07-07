# airmb-rag-backend

爱藏知识库管理后台的 FastAPI 后端服务。

## 技术栈

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x AsyncIO
- MySQL + aiomysql
- Alembic
- Pydantic Settings
- Redis / Celery（预留异步任务能力）

## 本地启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
fastapi dev
```

启动后访问：

- 健康检查：`http://127.0.0.1:8000/api/v1/health`
- Swagger：`http://127.0.0.1:8000/docs`
- ReDoc：`http://127.0.0.1:8000/redoc`

## 数据库配置

复制 `.env.example` 为 `.env`，再填写：

```env
DB_USER=
DB_PASSWORD=
```

应用启动时不会主动连接数据库。账号密码补齐后，再执行：

```powershell
alembic upgrade head
```

生成新迁移：

```powershell
alembic revision --autogenerate -m "describe change"
```

## 项目结构

```text
app/
├─ api/             # API 路由
├─ core/            # 配置、数据库和异常处理
├─ models/          # SQLAlchemy 模型
├─ repositories/    # 数据访问层
├─ schemas/         # Pydantic 请求/响应模型
├─ services/        # 业务逻辑
└─ workers/         # Celery 异步任务
```
