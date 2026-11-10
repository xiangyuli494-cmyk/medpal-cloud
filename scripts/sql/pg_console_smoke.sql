-- pg_console_smoke.sql —— RDS 控制台「SQL 窗口」兜底自检（无需公网连通）
-- 跑到最后会返回三张结果：建表/写入行数、两跳路径明细、路径总数。
-- 预期：写入 8 行；两跳路径明细里能看到 消化性溃疡 -> 胃镜 / 幽门螺杆菌 -> 呼气试验 等。

DROP TABLE IF EXISTS triple_smoke;

CREATE TABLE triple_smoke (
    triple_id    TEXT PRIMARY KEY,
    head_id      TEXT NOT NULL,
    head_label   TEXT NOT NULL,
    rel          TEXT NOT NULL,
    tail_id      TEXT NOT NULL,
    tail_label   TEXT NOT NULL,
    confidence   REAL DEFAULT 0.8,
    status       TEXT DEFAULT 'active'
);

-- 8 条种子三元组；ON CONFLICT 是 Postgres 方言（openGauss 血缘不支持，这里正好验它）
INSERT INTO triple_smoke (triple_id, head_id, head_label, rel, tail_id, tail_label, confidence) VALUES
  ('T-01','E-sym-001','上腹隐痛','提示','E-dis-001','消化性溃疡',0.86),
  ('T-02','E-dis-001','消化性溃疡','确诊检查','E-exam-001','胃镜',0.95),
  ('T-03','E-dis-001','消化性溃疡','常见病因','E-pat-001','幽门螺杆菌',0.92),
  ('T-04','E-pat-001','幽门螺杆菌','检测方法','E-exam-002','呼气试验',0.90),
  ('T-05','E-dis-001','消化性溃疡','就诊科室','E-dept-001','消化内科',0.98),
  ('T-06','E-dis-001','消化性溃疡','常见诱因','E-drug-001','布洛芬',0.84),
  ('T-07','E-sym-001','上腹隐痛','伴随症状','E-sym-002','烧心',0.80),
  ('T-08','E-pat-001','幽门螺杆菌','治疗方案','E-ther-001','根除治疗',0.88)
ON CONFLICT (triple_id) DO UPDATE SET confidence = EXCLUDED.confidence;

SELECT count(*) AS triples_written FROM triple_smoke;

-- 两跳遍历：从「消化性溃疡」出发，最多 2 跳
WITH RECURSIVE walk AS (
    SELECT t.tail_id   AS node_id,
           t.tail_label AS node_label,
           1           AS hops,
           t.head_label || ' -[' || t.rel || ']-> ' || t.tail_label AS path,
           t.confidence AS min_conf
    FROM triple_smoke t
    WHERE t.head_label = '消化性溃疡' AND t.status = 'active'
    UNION ALL
    SELECT t2.tail_id, t2.tail_label, w.hops + 1,
           w.path || ' -[' || t2.rel || ']-> ' || t2.tail_label,
           LEAST(w.min_conf, t2.confidence)
    FROM walk w
    JOIN triple_smoke t2 ON t2.head_id = w.node_id AND t2.status = 'active'
    WHERE w.hops < 2
)
SELECT hops, path, round(min_conf::numeric, 3) AS confidence
FROM walk
ORDER BY hops, path;

-- 路径总数（一次查询拿结论）
WITH RECURSIVE walk AS (
    SELECT t.tail_id AS node_id, 1 AS hops
    FROM triple_smoke t
    WHERE t.head_label = '消化性溃疡' AND t.status = 'active'
    UNION ALL
    SELECT t2.tail_id, w.hops + 1
    FROM walk w JOIN triple_smoke t2 ON t2.head_id = w.node_id AND t2.status = 'active'
    WHERE w.hops < 2
)
SELECT count(*) AS paths_within_2_hops FROM walk;

SELECT version() AS pg_version;
