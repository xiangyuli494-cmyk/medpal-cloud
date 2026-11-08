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
| 1 | **OBS 桶** | 存原件 + trace 报告（`obs://` 路径回写库） | 标准存储，单 AZ，1 GB 足够 | 对象存储服务 OBS → 创建桶 | `obs://medpal-trace-cn4` | ✅ **已开通并实测**（put/get/delete 三步自检通过，2026-11-03；2026-11-08 复核 listBuckets 仍 200） | t1 |
| 2 | **RDS for PostgreSQL** | 三元组 / 资产 / trace 元数据 | 单机 2C4G / 40 GB / 按需 | 云数据库 RDS → 购买实例 | `rds-61e6` / PG 18.6 | 🟡 **已开通并实测，实例已释放**（11/03 开通，`scripts/check_pg.py` 九步全绿；因按需计费 ¥0.46/h 于 11/06 删除，2026-11-08 API 复核 `total_count=0`；本地 `postgres:16` 容器保留同构环境） | t1 |
| 3 | **ModelArts Studio** | 大模型推理（结论叙述） | 按 token 计费，开通即用 | ModelArts Studio → 在线推理 → 获取 API Key | 端点 `https://api.modelarts-maas.com/v1` | ❌ **平台侧无可用对话模型**（2026-11-08 全流程探到底：① 域名 DNS 通，无 key → `400 ModelArts.81002`，假 key → `401 ModelArts.81003`，鉴权层正常；② 华北-北京四不支持该服务，须切华东-上海一 / 西南-贵阳一 / 中国-香港；③ 华东-上海一模型广场仅 8 个模型，搜 `deepseek` 命中 0；④ 西南-贵阳一模型广场 40 个，全为盘古 AI4S / 预测 / CV / Embedding **模型资产**，详情页只有「模型介绍 / 版本列表」，无 endpoint、无 API Key、无调用额度；⑤「预置服务」列表为空，顶部写明「并发 0 / 调用 0 次每天」；⑥ 要调用只能点「部署」→ 起算力 → 按小时计费。**结论：不接真模型**；`MEDPAL_LLM=offline` 的 FakeLLM 为默认，接入侧 3 个环境变量 + `scripts/smoke_llm.py` 已就绪，切真模型零代码改动） | t1 |
| 4 | **KooSearch** | 向量 / 语义检索（替代本地 BM25） | 最小规格集群 | 云搜索服务 KooSearch → 购买 | | ❌ **未申请**（服务入口只到 L0 白名单；检索走本地 BM25，`providers/huawei/koosearch.py` 未配置时返回空数组不抛错） | t1 |
| 5 | **计算与网关**（CCE + SWR + APIG） | 容器托管 + 镜像仓库 + 对外域名 | CCE 单节点（2C4G）+ SWR 免费额度 + APIG 共享版 | CCE / SWR / APIG 分别开通 | SWR 组织 `medpal` / 镜像 `swr.cn-north-4.myhuaweicloud.com/medpal/medpal-trace:0.1.0` | 🟡 **SWR 已完成**（镜像 50.3 MB，tag 0.1.0，2026-11-06 推送）；**CCE 未开通**（`clusters` 空；购买页默认 CCE Turbo 高可用 ¥2.91/h ≈ ¥70/天，且仅 master 不含节点；要建须切 CCE Standard + 单控制节点，master 免费只付节点 ≈ ¥0.4/h）；**APIG 未开通**（`/v2/{pid}/instances` 返回 404 APIGW.0101） | t1 |

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

## 4. 实测记录

> 下面两段输出是「云上确实通了」的证据，不是代码资产。
> `scripts/check_pg.py` 已随 B1 入库（#51），有真实 DSN 就能直接复跑；没有实例时用 `bash scripts/dev_pg.sh` 起本地 `postgres:16`。
> `scripts/check_obs.py` 未入库（#44 已关闭），4.1 的输出来自 2026-11-03 的一次性脚本；OBS 本身已于 11-08 用 SDK `listBuckets`/`headBucket` 复核通过。

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

## 5. 五项尝试的终局（2026-11-08 封盘）

| 资源 | 尝试到哪一步 | 终局 | 是否影响交付 |
| --- | --- | --- | --- |
| OBS | 建桶 → IAM 子用户 → SDK put/get/delete → 11/08 `listBuckets` / `headBucket` 复核 | ✅ **真跑通** | 不影响，T2 已在用 |
| RDS（PG 18.6） | 开通 → 绑 EIP → 安全组放行 → `check_pg.py` 九步全绿 → 按需成本删除 | ✅ **开过、验过、已释放** | 不影响，本地 `postgres:16` 同构 |
| ModelArts Studio | 六个入口逐个探到模型资产层 | ❌ **平台无可用对话模型** | 不影响，FakeLLM 兜底 |
| KooSearch | 服务入口停在 L0 白名单 | ❌ **放弃** | 不影响，BM25 兜底 |
| CCE + SWR + APIG | SWR 镜像已推；CCE 只到购买页；APIG 返回 404 | 🟡 **1/3** | 不影响，本机 Docker 演示 |

**一句话**：五项尝试全部走到底、每项都有可复核的证据与明确终局，没有一项是「没试」。真正开出来并在用的只有 OBS 与 SWR；RDS 验完即释放；ModelArts 与 KooSearch 卡在平台侧；CCE / APIG 是成本与时间取舍。

