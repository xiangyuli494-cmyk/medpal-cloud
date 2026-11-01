## 这个 PR 做了什么

<!-- 一句话说清；标题已带任务编号 -->

- 任务编号：C2
- 关联 issue：#12
- lane：底座 / 应用 / 云

## 改了哪些文件（reviewer 从这看起）

- `packages/core/medpal_core/...`
- `tests/test_xxx.py`

## 验收怎么跑

```bash
make pr
```

```text
粘贴真实输出，不要写「应该能过」
```

## 自查

- [ ] 分支从最新 `main` 切出，命名合规（`feat/C2-xxx`）
- [ ] diff ≤ 400 行
- [ ] 本地 `make pr` 通过
- [ ] 有测试或 smoke 脚本覆盖，且**离线**可跑（`bash tools/dev.sh all`）
- [ ] 文档同步（README / docs / deploy 该改的改了）
- [ ] 演示主路径没坏（演示页三条路径仍可一键触发）

## 给 reviewer 的提示

<!-- 你最希望对方重点看哪 3 行？哪块你自己也不确定？ -->
