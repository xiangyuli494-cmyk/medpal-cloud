# MedPal Trace

> 华为 ICT 创新赛 · 赛题1「基于华为云产品打造 AI 创新应用」参赛仓
> 一句话：**把医疗数据资产变成可推理、可追溯、可复用的智能底座。**
>
> 仓名取 trace（溯源）而不是 cloud：**我们做的是应用，不是云服务**。华为云是这套东西跑起来的底子，
> 卖点是那条每步都能核对的证据链 —— 换任何一朵云，能力都在；没有证据链，换个名字也不成立。

本仓是一个**新仓**，与团队既有的「院内智慧陪诊终端」（medpal）是两个独立仓库：
medpal 继续跑赛题3 的 Nexent 智能体线，本仓只承载赛题1。底座**复制**过来而不是搬走，
medpal 一行不动。为什么要新开一个仓、复用了哪些、边界怎么卡，见
[docs/03-复用清单.md](docs/03-复用清单.md)。

---

## 1. 它解决什么问题

医院里有的是文档，缺的是「能拿去推理的资产」：一份临床路径 PDF，人和模型都能读，
但没人说得清「这句话来自哪份文件第几段」，也就没人敢把结论写进病历。

本仓做三件事：

1. **资产化**：文件进来 → 解析成带锚点（`asset_id#anchor`）的块 → 实体抽取 → 资产卡入账。
2. **可推理**：锚点连成本体三元组，支持多跳查询（症状 → 疾病 → 检查/科室/用药）。
3. **可追溯**：每次回答都落一条决策链 `TR-YYYYMMDD-XXXX`，每一步引用真实锚点或三元组 ID；
   核对不到的进 `unresolved`，完整率 = `1 - unresolved/cited`；拒答题（零引用）报告里写「—（拒答，不计分）」，
   评测按 0 分记，演示页也不画成 100%。

演示站首页就是这条链：输入一句问诊话术，右栏输出结论、决策链、以及 100% 的证据可核对率。

---

## 2. 30 秒跑起来

前置：Python ≥ 3.11。

~~~bash
git clone <REPO_URL> medpal-trace && cd medpal-trace
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

bash tools/dev.sh seed                                  # 灌合成样本 + 8 条演示三元组 + 打 v1.0 快照
bash tools/dev.sh api                                   # http://127.0.0.1:8000/  （演示页在 /web/）
bash tools/dev.sh all                                   # seed + 30 项测试 + 边界检查 + 评测
~~~

不便装依赖也行 —— **离线默认零外部服务**：SQLite 存本体，BM25 做召回，FakeLLM 占位，
不接华为云也能把整条链和全部测试跑完。这决定了「评委能不能当场复现」这件事没有悬念。

`tools/dev.sh` 会自己把 `PYTHONPATH` 设成当前系统认的形状（Windows 用分号 + 反斜杠，
POSIX 用冒号 + 斜杠），所以不用手写路径。想直接 `python -m app.seed` 的话，
得先 `export PYTHONPATH` 指到 `packages/core` 和 `apps/api`；
没装 `make` 也不影响，`Makefile` 只是 `dev.sh` 的等价快捷键。

---

## 3. 结构：core 是底座，apps 是外壳

~~~text
medpal-trace/
├── packages/core/medpal_core/        # 底座（不许 import apps，不许出现行业术语）
│   ├── contracts/                    # 协议层：Step/Trace 数据结构 + trace.schema.json + 校验器
│   ├── assets/                       # 资产层：parsers（多模态解析）/ entity（词表驱动）/ card（入库）
│   ├── ontology/                     # 知识层：三元组、多跳查询、版本快照与差分、标准对齐
│   ├── retrieval/                    # 召回层：Retriever 协议 + 零依赖 BM25
│   ├── trace/                        # 决策链：落库 + 报告 + 溯源完整率
│   ├── llm/                          # 模型层：FakeLLM / OpenAI 兼容（ModelArts Studio、盘古）
│   ├── providers/huawei/             # 云适配：OBS / GaussDB / ModelArts / KooSearch
│   └── storage/                      # 存储基座：SQLite 连接与路径（环境变量驱动）
├── apps/api/app/                     # FastAPI：pipeline + 六个端点 + seed
├── apps/web/index.html               # 单文件演示页（无构建、无依赖）
├── data/                             # 词表、合成样本、本体种子
├── eval/                             # 评测集与指标脚本
├── tests/                            # 30 项测试，含边界检查自身的测试
├── tools/                            # check_boundaries / check_guard_words / dev.sh
└── docs/                             # 赛题理解、架构、云映射、复用清单、路线图
~~~

**依赖方向只有一条**：`apps → medpal_core → 标准库 / 厂商 SDK（仅 providers）`。

---

## 4. 华为云怎么接（五点插槽）

| 能力 | 本地默认（离线可跑） | 华为云 | 适配位置 |
| --- | --- | --- | --- |
| 模型 | FakeLLM | ModelArts Studio / 盘古（OpenAI 兼容） | `providers/huawei/modelarts.py` |
| 存储 | SQLite 单文件 | GaussDB(for openGauss) | `providers/huawei/gaussdb.py` |
| 对象存储 | 本地 `data/` | OBS | `providers/huawei/obs.py` |
| 检索 | BM25 | KooSearch | `providers/huawei/koosearch.py` |
| 计算/网关 | uvicorn | FunctionGraph 或 CCE + APIG | `docs/02-华为云映射.md` |

切换方式是**改环境变量，不改代码**：

~~~bash
export MEDPAL_LLM=openai
export MEDPAL_LLM_BASE_URL=https://<MODELARTS_ENDPOINT>/v1
export MEDPAL_LLM_MODEL=<MODEL_NAME>
export MEDPAL_LLM_API_KEY=$HUAWEI_AK
export HUAWEI_OBS_BUCKET=<BUCKET>
export HUAWEI_GAUSSDB_DSN=postgresql://<USER>:<PASS>@<HOST>:<PORT>/<DB>
~~~

没配就自动回落本地实现，不会因为「没上云」而跑不起来 —— 也不会假装成功：
`HuaweiConfig.readiness()` 会明确告诉你哪块云服务还缺哪个变量。

---

## 5. 评测口径

~~~text
$ python eval/run_eval.py
OK  上腹隐痛伴反酸，下一步做什么检查？         completeness=1.0  12ms
OK  反复上腹隐痛，怀疑幽门螺杆菌，怎么查？     completeness=1.0  9ms
...
dept_acc=1.0  exam_recall=1.0  completeness=1.0  avg_steps=6.5  avg_ms=11.3  (n=6)
~~~

数据集现在只有 6 条合成样本，规模小，但**口径是真的**：加 jsonl 行就能扩，评委可当场重跑。
不刷分，只求「同样输入、同样输出」。

---

## 6. 三条架构边界（机器检查，不是文档口号）

`python tools/check_boundaries.py` 在 CI 里跑，红一条就卡：

- **BND1** `packages/core` 不得 import 应用层 —— 保底座可复用。
- **BND2** 云厂商 SDK 只许出现在 `providers/` —— 保「换云只换一个目录」。
- **BND3** core 的可执行代码里不得出现行业术语（词表里的词）—— 保「与行业无关」。
  注释和 docstring 不算，那里出现是解释；代码里出现才是耦合。

另有 `tools/check_guard_words.py` 扫 README / docs / 样本 / 演示页，
拦下「疗效承诺」「绝对化表述」这类医疗文案禁用语（清单在 `tools/guard_words.txt`）。

---

## 7. 数据与合规

- `data/samples/` 下全部是**自拟合成样本**，不含真实患者数据，不作为临床依据。
- 资产卡带 `sensitivity` 字段（`public` / `synthetic`），为后续接真实数据留了分级位。
- 每条结论都附证据锚点，缺证据时宁可标注缺口，也不给无出处的断言。

---

## 8. 团队与分工

3 人：**t1** `xiangyuli494-cmyk`（队长，底座 / 方案书 / 答辩）、**t2** `suyouZJF`（应用与评测）、
**t3** `zincumyu`（云与交付，硬活都排他）。

仓库：<https://github.com/xiangyuli494-cmyk/medpal-trace>

`main` 是保护分支：**改动一律走 PR，1 人 approve 才合并，只有队长点 merge**，直推和无评审合并都被 GitHub 挡掉。

已生效（实测直推被拒：`protected branch hook declined`）：PR 必须、approve=1、新提交作废旧 approve、4 个必绿检查（`test (3.11)` `test (3.12)` `meta` `size`）、必须 rebase 到最新 main、对话全解、禁强推、禁删分支、管理员同样受限（`enforce_admins`）。

入队两件事：①（**已完成**）t2/t3 已加成 **Write** 协作者；②t2/t3 首次克隆后 `git remote add upstream https://github.com/xiangyuli494-cmyk/medpal-trace.git`，每天 `git pull --rebase upstream main`。

- 逐条任务与**验收标准**：[docs/05-任务看板.md](docs/05-任务看板.md)
- 分支 / review / approve / 合并规则：[docs/06-协作与分支规范.md](docs/06-协作与分支规范.md)
- 节奏、Gate、裁剪顺序：[docs/04-路线图.md](docs/04-路线图.md)
- 云资源申请与就绪状态：[docs/cloud-resources.md](docs/cloud-resources.md)
