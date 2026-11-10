# 部署与复现（B13）

> 目标：**拿到仓库的人照着本文从上到下能把系统跑起来**。
> 三条路线按「验证到什么程度」分开写，**没跑过的会明确标「未实测」** —— 这份文档里没有一句「应该可以」。

- 代码基线：`main` @ `2dc0b87`（2026-11-10）
- 前置：git、bash（Windows 用 Git Bash）、Python 3.11 或 3.12
- 本机实测环境：Windows 11 + Python 3.12 + Git Bash，SQLite 后端，无任何华为云变量

## 0. 先选路线

| 路线 | 用途 | 验证状态 |
| --- | --- | --- |
| **A 本地 venv** | 开发、答辩兜底、评委复现 | ✅ **本机从零实测通过（200 秒）** |
| B 容器 | 单机交付、上云前置 | ⚠️ **未实测**（本机 Docker daemon 未启动），`Dockerfile` 与命令已就绪 |
| C 云上 SWR → CCE → APIG | 线上形态 | ⚠️ **未落地**，依赖 B10/B11，见 §3 的待办清单 |

> 答辩如果只演示本地，**只走路线 A 就够了**，3 分钟能起完整系统。

---

## 1. 路线 A：本地从零（已实测）

### A1. 拿代码

```bash
git clone <repo-url> medpal-trace && cd medpal-trace
git log --oneline -1        # 预期打印出一行 main 上的提交
```

### A2. 建虚拟环境并装依赖

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash；Linux/macOS 用 .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"
```

> 这一步是大头：**本机约 173 秒**（依赖下载）。国内网络慢就换镜像源
> `-i https://pypi.tuna.tsinghua.edu.cn/simple`。

### A3. 灌演示数据

```bash
python -m app.seed
```

预期：打印一段 JSON，含 `"asset_id": "AST-2026-xxxxxx"`、`"triples_added": 8`、
`"snapshot": {"version": "v1.0", "triple_count": 8, ...}`，并生成 `data/medpal.db`（约 60 KB）。

### A4. 起服务

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

预期日志最后一行：`Uvicorn running on http://127.0.0.1:8000`。

### A5. 三条冒烟（另开一个终端）

```bash
# 1) 健康检查
curl -s http://127.0.0.1:8000/health
# 预期：{"ok":true,...,"ontology_version":"v1.0","assets":1,"storage":"sqlite",...}

# 2) 真提问（Windows Git Bash 下 POST 带中文必须用 --data-binary，见 §5）
cat > /tmp/q.json <<'EOF'
{"question": "上腹隐痛伴反酸，下一步做什么检查？", "top_k": 8, "max_hops": 2}
EOF
curl -s --data-binary @/tmp/q.json -H 'Content-Type: application/json' -X POST http://127.0.0.1:8000/v1/ask
# 预期：conclusion.dept = "消化内科"，evidence_count = 8，trace_completeness = 1.0

# 3) 演示页
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/web/
# 预期：200
```

浏览器打开 `http://127.0.0.1:8000/web/`，应看到结论 / 完整率 / 决策链 / 证据清单四块；
页脚三个「演示入口」（默认 / 加载 / 拒答）可一键切三态。

### A6. 一键验收

```bash
bash scripts/verify.sh --fast      # 约 17 秒：lint → 边界 → 禁用语 → pytest → seed → 冒烟
MIN_N=60 bash scripts/verify.sh    # 全量，含 n=60 评测门槛
```

预期最后一行 `PASS`、退出码 0。

> 更细的 17 条端到端检查（每条含命令与期望输出）见 **`tests/e2e.md`**，想逐项验收就照它跑。

---

## 2. 路线 B：容器（未实测）

`Dockerfile` 已就绪（一个镜像同时承载 API 与演示页，环境变量决定后端实现）。

```bash
docker build -t medpal-trace:0.1.0 .
docker run -p 8000:8000 -e MEDPAL_LLM=offline -v "$PWD/data:/app/data" medpal-trace:0.1.0
curl -s http://127.0.0.1:8000/health
```

**为什么标未实测**：本机 Docker Desktop 的 daemon 没启动（`docker info` 报
`failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`），
且 B5「镜像可构建可运行」还没合。静态检查过两处：`pyproject.toml` 的
`package-dir = { "" = "packages/core" }` 让 `pip install -e .` 只装 `medpal_core`，
`app` 靠镜像里的 `PYTHONPATH=/app/apps/api`；两者路径与 Dockerfile 一致 ——
但**没有真构建过，所以不写「验证通过」**。

---

## 3. 路线 C：云上 SWR → CCE → APIG（未落地）

要先把下面几件事做完，本文才能从「清单」变成「步骤」：

| 依赖 | 内容 | 负责人 | 状态 |
| --- | --- | --- | --- |
| B5 | 镜像可构建可运行 | t3 | 未完成 |
| B6 | GaussDB 真机迁移 | t3 | 未完成 |
| B7 | OBS 真机上传 / 回读 | t3 | 未完成 |
| B10 | 推 SWR + 部署 CCE | t3 | 未完成 |
| B11 | APIG 域名 + 限流 | t3 | 未完成 |

**已经就绪、现在就能用的部分**（只是还没串起来）：

- 镜像入口：`Dockerfile` 的 `CMD` 起 `uvicorn`，`EXPOSE 8000`，带 `HEALTHCHECK`；
- 配置模板：**`.env.huawei.example`**（复制成 `.env.huawei` 填值，`.gitignore` 已挡真实凭据）；
- 建表：`python -c "from medpal_core.providers.huawei.gaussdb import connect, prepare; c=connect(); prepare(c); print('schema ready')"`；
- 就绪度自检：`bash scripts/dev.huawei.sh`（缺变量打印「缺 XXX」并退出码 1；变量齐时校验
  `/v1/cloud` 的 `ready.gaussdb=true` 与 `/health` 的 `storage=gaussdb`）。

推导出的镜像命令（**等 B5/B10 完成后照此执行，当前未验证**）：

```bash
docker tag medpal-trace:0.1.0 swr.cn-north-4.myhuaweicloud.com/<ORG>/medpal-trace:0.1.0
docker push swr.cn-north-4.myhuaweicloud.com/<ORG>/medpal-trace:0.1.0
kubectl -n <NS> set env deploy/medpal-trace --from=secret/medpal-huawei   # 变量见 .env.huawei.example
kubectl -n <NS> rollout status deploy/medpal-trace
```

云上跑起来之后的验收命令与路线 A 相同（只换 host），见 §4。

---

## 4. 上线自检（任何路线都跑这四条）

```bash
B=http://127.0.0.1:8000          # 云上换成 APIG 域名
curl -s $B/health
curl -s $B/v1/cloud              # 看 ready 四项与 missing，二者必须自洽
curl -s --data-binary @/tmp/q.json -H 'Content-Type: application/json' -X POST $B/v1/ask
curl -s -o /dev/null -w '%{http_code}\n' $B/web/
```

判定线：

- `/health` 的 `storage` 与 `/v1/cloud` 的 `storage_backend` 必须一致（都是 `sqlite` 或都是 `gaussdb`）；
- `/health` 的 `llm` 还是 `offline`，就说明模型变量没生效 —— 别急着演示，先看 `/v1/cloud` 的
  `missing` 指向哪个变量；
- `/v1/ask` 的 `evidence_count > 0` 且 `trace_completeness == 1.0`。

---

## 5. 故障排查（按出现频率排）

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `ModuleNotFoundError: No module named 'medpal_core'` | 不在 `packages/core` 路径上 | `pip install -e .`，或设 `PYTHONPATH` 指向 `packages/core` 与 `apps/api`（`scripts/verify.sh` 会自动设） |
| `ModuleNotFoundError: No module named 'app'` | `apps/api` 不在 `PYTHONPATH` | 同上；Windows Git Bash 要 `cygpath -w` 转成 Windows 路径并用**分号**分隔 |
| `curl -d '{…中文…}'` 返回 `There was an error parsing the body` | Git Bash 把中文 argv 交给 Windows ANSI 码页（实测发出 57 字节 vs 正确 64 字节） | 用 `--data-binary @文件`；Linux/macOS 无此问题 |
| `sqlite3.IntegrityError: UNIQUE constraint failed: trace.trace_id` | 后四位只有 65536 种，累积几百条后必撞；修复在 PR #74 | 清库重跑：`rm -f data/medpal.db && rm -rf data/reports && python -m app.seed` |
| 并发请求随机 500，日志 `SQLite objects created in a thread can only be used in that same thread` | issue #69：FastAPI 把同步依赖与端点调度到不同线程，`sqlite3.connect` 未开 `check_same_thread=False` | 串行验收不受影响；演示页会并发，等 #69 修完再放心演示 |
| 端口被占，服务"看起来起来了"但数据不对 | 请求打到了别人的进程 | 换端口 `--port 8001`，先查占用再起 |
| `.env.huawei` 里的值带 `\r` 连不上库 | Windows 编辑器存成 CRLF | `scripts/dev.huawei.sh` 已用 `sed 's/\r$//'` 归一；手工 source 时注意 |

---

## 6. 实测耗时（文末记录）

**路线 A 从零到 `verify.sh --fast` 通过：3.3 分钟（200 秒）。**

| 步骤 | 实测耗时 | 备注 |
| --- | --- | --- |
| A1 克隆代码 | 1 秒 | 本地克隆；公网克隆视网速 |
| A2 venv + `pip install -e ".[dev]"` | **173 秒** | 唯一的大头，依赖下载；有缓存会快很多 |
| A3 `python -m app.seed` | 2 秒 | 生成 `data/medpal.db`（61 KB） |
| A4 起服务到 `/health` 就绪 | 4 秒 | `uvicorn` 单进程 |
| A5 三条冒烟 | 1 秒 | health / ask / web 全通过 |
| A6 `verify.sh --fast` | 17 秒 | 含 pytest 53 项 |
| **合计** | **200 秒 ≈ 3.3 分钟** | 第 2 步占 86% |

实测环境：Windows 11 / Python 3.12 / Git Bash / SQLite / 无华为云变量。
冒烟结果：`health ok:true`、`dept=消化内科 evidence=8 completeness=1.0`、`web_http=200`、`verify PASS`。

> 换台机器复现时，**只有 A2 的耗时会明显不同**（网络与依赖缓存），其余五步都在秒级。
> A2 如果超过 10 分钟，先怀疑镜像源，别怀疑代码。

## 7. 已知未覆盖（写清楚比藏着好）

- **路线 B 的镜像从未被构建过**（本机 daemon 未启动 + B5 未合）——上云前必须补这次构建验证；
- **路线 C 的五个依赖全部未完成**，上面的 `kubectl` 命令是按现有 Dockerfile/配置推断的，
  等 B10/B11 落地后需要按真实集群名/命名空间/Secret 名重写；
- 云端四项（OBS / GaussDB / ModelArts / KooSearch）**当前全部未接真机**，`/v1/cloud` 会如实报 `ready` 全 false，
  这不是部署错误，是还没配。
