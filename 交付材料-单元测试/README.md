# 交付材料 · 单元测试

对应赛题要求：**单元测试用例（覆盖率 ≥ 60%）**。部署材料在同级的 `交付材料-Docker部署/`。

## 结论

```
161 passed, 2 warnings in 205.55s
Required test coverage of 60.0% reached. Total coverage: 78.79%
TOTAL  10522 语句  2232 未覆盖  79%
```

**161 项测试全部通过，语句覆盖率 78.79%**，高于要求的 60%。

「覆盖率 ≥ 60%」指**代码覆盖率**——单元测试执行到的代码语句占比，属交付完整性要求，非安全测试。
结果在完整代码上运行得出。

## 材料

| 类别 | 材料 | 位置 |
| --- | --- | --- |
| 测试代码 | 38 个测试文件 | 仓库 `backend/tests/`（不在本目录重复一份，避免与源码脱节） |
| 测试说明 | 测试范围、门禁配置、复现命令、四个挂载的必要性 | [`单元测试报告.md`](单元测试报告.md) |
| 测试结果 | pytest 原始输出（含逐文件覆盖率） | [`单元测试输出.txt`](单元测试输出.txt) |
| 测试结果 | 覆盖率 HTML 报告，浏览器打开 `index.html` | [`coverage/`](coverage/) |

覆盖率报告中，未包含实现的模块只给汇总数字、不附逐行标注；汇总页的文件清单与全部
覆盖率数字未作改动。

## 门禁

阈值写死在 `backend/pyproject.toml`，低于 60% 直接判失败，不依赖人工检查：

```toml
[tool.coverage.run]
source = ["app"]
omit = ["app/infrastructure/*"]   # 外部网关（LLM、HTTP 抓取）不计入，避免用桩测试凑覆盖率

[tool.coverage.report]
fail_under = 60
```

## 打包注意

`coverage/` 是 `pytest --cov-report=html` 的产物，随代码变化即失效，因此**不入 git**
（coverage.py 会在该目录内自带 `.gitignore`）。从仓库克隆的副本里没有它，打包前确认本地已生成，
或按 [`单元测试报告.md`](单元测试报告.md) 的命令重新生成。归档证据以 `单元测试输出.txt` 为准。
