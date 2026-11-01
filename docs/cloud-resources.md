# 云资源申请与就绪表（C0 · 11/02 发出）

> 这是关键路径的第一环：**C0 不发出，B6 GaussDB 就开不了工，整条链往后滑**。
> 每拿到一项就把「工单号 / 状态」填上，11/08 前至少 OBS + GaussDB + ModelArts 三项为「已开通」。

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
| 1 | **OBS 桶** | 存原件 + trace 报告（`obs://` 路径回写库） | 标准存储，单 AZ，1 GB 足够 | 对象存储服务 OBS → 创建桶 | | ☐ 未申请 | t1 |
| 2 | **GaussDB** | 三元组 / 资产 / trace 元数据 | 集中式版 1 主 1 备，最小规格 | 云数据库 GaussDB → 购买实例 | | ☐ 未申请 | t1 |
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
| `HUAWEI_GAUSSDB_DSN` | `host=... port=8000 dbname=... user=... password=...` | |
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