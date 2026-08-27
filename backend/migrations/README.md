# Alembic migrations

```powershell
cd backend
.\.venv\Scripts\alembic.exe upgrade head
```

迁移脚本是空库初始化的唯一执行入口。`database/target_schema_v1_mysql8.sql`继续作为完整目标结构设计基线，后续按模块逐批转换为Alembic迁移。

