# 部署到华为云（骨架，P1 落地）

镜像就绪后，最省事的路径是 **SWR → CCE → APIG**；演示期也可以先用 ECS 直接 `docker run`。

## 1. 构建并推镜像

~~~bash
docker build -t medpal-cloud:0.1.0 .
docker tag medpal-cloud:0.1.0 swr.cn-north-4.myhuaweicloud.com/<ORG>/medpal-cloud:0.1.0
docker push swr.cn-north-4.myhuaweicloud.com/<ORG>/medpal-cloud:0.1.0
~~~

## 2. 准备云资源

| 资源 | 用途 | 需要的环境变量 |
| --- | --- | --- |
| GaussDB(for openGauss) | 本体 + 决策链 | `HUAWEI_GAUSSDB_DSN` |
| OBS 桶 | 原件与报告 | `HUAWEI_OBS_BUCKET` + AK/SK |
| ModelArts Studio | 结论自然语言化 | `MEDPAL_LLM_BASE_URL` / `_MODEL` / `_API_KEY` |
| KooSearch | 锚点召回 | `HUAWEI_KOOSEARCH_ENDPOINT` |
| CCE + APIG | 跑容器 + 对外网关 | — |

## 3. 建表

~~~bash
python -c "from medpal_core.providers.huawei.gaussdb import connect, prepare; \
c = connect(); prepare(c); print('schema ready')"
~~~

## 4. 上线自检

~~~bash
curl -s https://<APIG_HOST>/health | python -m json.tool   # llm 应该是 modelarts，不是 offline
curl -s -X POST https://<APIG_HOST>/v1/ask -H 'content-type: application/json' \
     -d '{"question":"上腹隐痛伴反酸，下一步做什么检查？"}'
~~~

`/health` 里 `llm` 还写着 `offline`，就说明变量没生效 —— 这时别急着演示，
先看 `HuaweiConfig.readiness()` 报的是哪一项。
