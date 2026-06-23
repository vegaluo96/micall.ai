# 数据库（Postgres + pgvector）—— 真实数据持久化

配了 `database.dsn`，后端就从「内存仓储（重启即丢、全用户共用 _ANON）」切到 **Postgres 持久化**：
记忆/画像/音色/角色/用户/通话/计费都落库。没配则继续用内存（演示可用，重启丢）。

> **表/扩展是自动建的**：后端开机时 `PgRepository` 会自己跑 schema 建好所有表（无需手动建表）。
> 你只需要把「Postgres 引擎本身」准备好 + 给一个 dsn。以下三选一。

## 一、准备 Postgres（三选一，A/B 全自动）

**A. 服务器自建 · 一条命令（推荐，Ubuntu/Debian）**
在服务器上跑（装 PG+pgvector、建库建角色、启用扩展、自动把 dsn 写进 micall.env）：
```bash
cd ~/micall.ai
sudo bash deploy/setup_db_server.sh
sudo systemctl restart micall-backend     # 重启 → 后端自动建表
```
幂等，可反复跑。自定义库名/账号：`sudo DB_NAME=micall DB_USER=micall DB_PASS=xxx bash deploy/setup_db_server.sh`。

**B. Docker · 一条命令（不想动系统包就用这个）**
```bash
cd ~/micall.ai/deploy
docker compose -f docker-compose.db.yml up -d     # 起一个带 pgvector 的 Postgres
```
再把 dsn（改掉密码）写进 `backend/config/micall.env`，重启后端。

**C. 阿里云 RDS PostgreSQL（托管，省运维）**
1. 控制台建 PostgreSQL 实例（与后端同地域），建库 `micall` + 账号，后端服务器 IP 加白名单。
2. 控制台「插件管理」启用 **pgvector**（`vector`）扩展。
3. 把 dsn 写进 micall.env（见第三步）。

## 二、（可选）手动建表
A 用脚本、后端开机都会自动建表，正常**不需要**这步。要单独验证可跑：
```bash
cd ~/micall.ai/backend && pip3 install -r requirements.txt
export MICALL_DATABASE_DSN='postgresql://micall:密码@主机:5432/micall'
PYTHONPATH=src python3 scripts/init_db.py        # 输出「✓ 建库完成。表：…」即成功
```

## 三、让后端用上（写进 micall.env，重启）
把连接串写进 `backend/config/micall.env`（gitignored，不入库）：
```
MICALL_DATABASE_DSN=postgresql://micall:密码@主机:5432/micall
```
```bash
sudo systemctl restart micall-backend
journalctl -u micall-backend -n 10 --no-pager   # 应看到「仓储：Postgres 持久化已启用」
```
没看到这行就是没连上（dsn 错/白名单/防火墙）——会自动回退内存并告警，通话仍可用。

## 四、向量维度要对齐
`facts.embedding` 是 `vector(1024)`。它**必须等于所配 Embedding 模型的输出维度**——后台「接口配置」
点 Embedding 的「测试连接」会显示维度（text-embedding-v4/v3 默认 1024，正好）。若你换了模型导致维度
不同，改 `schema.sql` 里 `vector(N)` 重新 `init_db.py`，并清空 facts（旧向量作废）。

## 备份与安全
- DB 密码只进 `micall.env`，绝不入库（铁律2）。
- 定期备份：`pg_dump micall > micall_$(date +%F).sql`（RDS 有自动备份，开着即可）。
