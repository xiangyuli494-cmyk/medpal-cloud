# 云资源申请与就绪表（C0 · 11/02 发出）

> 这是关键路径的第一环：**C0 不发出，B6 GaussDB 就开不了工，整条链往后滑**。
> 每拿到一项就把「工单号 / 状态」填上，11/08 前至少 OBS + RDS + ModelArts 三项为「已开通」（**11/03 已完成 OBS 与 RDS，见 §4 实测记录**）。

## 0. 申请前先确认（缺一项会卡住审批）

| 项 | 说明 | 状态 |
| --- | --- | --- |
| 华为云账号 | 已实名认证（个人或学校项目账号） | ☐ |
| 项目 ID | 「我的凭证」里复制 `project_id`，填进 `HUAWEI_PROJECT_ID` | ☐ |
| Region | 统一用 **cn-north-4（北京四）**，四处资源必须同区，否则内网不通 | ☐ |
| 代金券 / 预算 | 校园赛一般有代金券，先确认额度能撑 4 周 | ☐ |
| IAM 子账号 | 给 t2 建一个可管 OBS/GaussDB/CCE 的子账号，别共用主账号密钥 | ☐ |

## 1. 五项资源（一行一项，共 5 行）

| # | 资源 | 用途 | 最低规格 | 申请入口 | 工单号 | 状态 | 负责人 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | **OBS 桶** | 存原件 + trace 报告（`obs://` 路径回写库） | 标准存储，单 AZ，1 GB 足够 | 对象存储服务 OBS → 创建桶 | `obs://medpal-trace-cn4` | ✅ **已开通 11/03** | t1 |
| 2 | **RDS for PostgreSQL** | 三元组 / 资产 / trace 元数据 | 单机 2C4G / 40 GB / 按需（¥0.46 每小时） | 云数据库 RDS → 购买实例 | `rds-61e6` / PG 18.6 | ✅ **已开通 11/03** | t1 |
| 3 | **ModelArts Studio** | 大模型推理（结论叙述） | 按 token 计费，开通即用 | ModelArts Studio → 在线推理 → 获取 API Key | | ☐ 未申请 | t1 |
| 4 | **KooSearch** | 向量 / 语义检索（替代本地 BM25） | 最小规格集群 | 云搜索服务 KooSearch → 购买 | | ☐ 未申请 | t1 |
| 5 | **计算与网关**（CCE + SWR + APIG） | 容器托管 + 镜像仓库 + 对外域名 | CCE 单节点（2C4G）+ SWR 免费额度 + APIG 共享版 | CCE / SWR / APIG 分别开通，同一工单跟进 | | ☐ 未申请 | t1 |

## 2. 拿到之后填这里（供 `/health` 与 `dev.huawei.sh` 读取）

| 环境变量 | 含义 | 值 |
| --- | --- | --- |
| `HUAWEI_AK` / `HUAWEI_SK` | IAM 子账号密钥 | （不入库，写 `.env.huawei`） |
| `HUAWEI_REGION` | 区域 | cn-north-4 |
| `HUAWEI_PROJECT_ID` | 项目 ID | |
| `HUAWEI_OBS_BUCKET` | 桶名 | |
| `MEDPAL_DB_DSN` | `postgresql://root:***@<地址>:5432/medpal`（通用名优先；旧名 `HUAWEI_GAUSSDB_DSN` 仍兼容） | |
| `HUAWEI_MODEL_ENDPOINT` / `HUAWEI_MODEL_NAME` | 推理地址与模型名 | |
| `HUAWEI_KOOSEARCH_ENDPOINT` | 搜索服务地址 | |

## 3. 拿不到时的降级（照 [docs/04-路线图.md](04-路线图.md) §7 的顺序砍）

| 拿不到 | 降级做法 | 影响 |
| --- | --- | --- |
| KooSearch 批不下来 | 继续用本地 BM25，方案书里写「可切换检索后端」并给对比表 | 少一个云产品，演示不受影响 |
| CCE 批不下来 | 单台 ECS + `docker run`，APIG 仍接上 | 少了容器编排的描述 |
| GaussDB 批不下来 | 本地 Postgres 16（B1 已跑通），保留方言差异说明 | **最痛**，三云真机只剩两云 |
| ModelArts 额度不够 | 演示用 `FakeLLM` + 预录一段真机调用视频 | 结论叙述变成离线文案 |

> 三项**不可降级**：OBS、GaussDB、ModelArts 的真机调用记录（评分要「用了华为云」，不是「写了华为云」）。

## 4. 实测记录（2026-11-03）

证据原文存在 [docs/evidence/2026-11-03-cloud.md](evidence/2026-11-03-cloud.md)。

### 4.1 OBS：能写能读能删

```
$ python scripts/check_obs.py
put    [OK] _selftest/hello.txt (200)
get    [OK] 内容一致
delete [OK]
OBS READY: obs://medpal-trace-cn4/_selftest/hello.txt @ cn-north-4
```

### 4.2 RDS：`scripts/check_pg.py` 九步全绿

```
$ python scripts/check_pg.py
3) 连接      [OK] PostgreSQL 18.6 on x86_64-pc-linux-gnu
4) 建表      [OK] 表：alias, asset, pending_diff, trace, triple, version
5) 写资产    [OK] 覆盖后 title = PG 自检资产 v2
6) 写三元组  [OK] triple_id = T-6496a4bd
7) 版本快照  [OK] v-pgtest triple_count=1 hash=07ea7173fa357dec
8) 读回      [OK] list_assets 命中，当前共 1 条
9) 清理      [OK]
PG READY: 123.60.223.151:5432/medpal
```

### 4.3 云上踩到的四个坑（本地都测不出来）

| # | 现象 | 根因 | 正解 |
| --- | --- | --- | --- |
| 1 | 桶名带 `.`，SDK 连建连接都证书失败 | 桶名含点会让访问域名变成两级子域，泛域名证书只覆盖一级 | 桶名不带点：`medpal-trace-cn4` |
| 2 | `get` 返回 200 但内容是空的 | `esdk-obs-python` 的 `getObject` 不传 `loadStreamInMemory=True` 时，`resp.body` 是 `buffer=None` 的 `ObjectStream`，`read` 属性也是 `None` | provider 加 `read_body()` 兜底并显式传 `loadStreamInMemory=True` |
| 3 | 接上 RDS 立刻 `syntax error` | `INSERT OR REPLACE` 是 SQLite 私有语法，PG 不认 | 改成 `INSERT ... ON CONFLICT ... DO UPDATE`，两库通用 |
| 4 | `permission denied for schema public` | PostgreSQL **15+** 起默认收回了 `PUBLIC` 对 `public` schema 的 `CREATE`；且默认库 `postgres` 的 owner 是 `rdsAdmin` 不是 `root` | 建一个属于 `root` 的库：`CREATE DATABASE medpal;`，之后代码自动建表，不需要任何授权语句 |

### 4.4 新环境初始化只需一句 SQL

```sql
-- 在 DAS 的 SQL 窗口执行一次；root 是建库者，随后即拥有该库 public schema 的建表权
CREATE DATABASE medpal;
```

然后：

```bash
export MEDPAL_DB_DSN="postgresql://root:***@<地址>:5432/medpal"
export MEDPAL_DB_BACKEND=postgres
python scripts/check_pg.py
```

### 4.5 公网访问的成本纪律

- 只有本机验证才需要绑 EIP：`¥0.02（IP 保有费）+ ¥0.063（1 Mbit/s 带宽）= ¥0.083/小时`
- **验完三件事一起做**：解绑 EIP → 在 EIP 控制台**释放**（只解绑照收钱）→ 实例「停止」（停机只收存储费）
- 安全组只放自己的出口 IP：`<本机公网IP>/32`，不要 `0.0.0.0/0`
