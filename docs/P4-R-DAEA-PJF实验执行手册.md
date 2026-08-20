# P4：R-DAEA-PJF 实验执行手册

## 1. 冻结原则

- 先冻结测试集，再运行系统；测试集不得用于改提示词、阈值或词表。
- 简历和“简历—岗位”样本均采用双人独立标注；不一致项由第三人裁决。
- DeepSeek 只生成带原文引用的候选事实。技术 L3 映射、证据等级、区间、十维分数和标签均由本地代码计算。
- 主实验记录模型名、提示版本、算法版本、岗位规则版本和输入哈希。
- OCR 扫描件单列报告，不与可复制文本格式混算 90% 主指标。

## 2. 第一批必须完成的实验

### 2.1 简历提取冻结集

建议至少 120 份脱敏简历：文本 PDF、DOCX、TXT 各 30 份，扫描 PDF 30 份。前三类组成主测试集，扫描 PDF 是 OCR 边界集。

每份简历标注五类实体：`name`、`education`、`experience`、`project`、`skill`。每条实体记录标准值和最短原文证据。姓名可用稳定假名替换，但标注值和原文必须一致。

主指标：实体级 micro Precision、Recall、F1；按五类实体分别报告。达标条件为主测试集 micro-F1 ≥ 0.90，同时报告原文引用有效率。扫描件只报告 OCR 后结果和失败类型。

### 2.2 人岗匹配冻结集

建议至少 300 对“简历—岗位”，三类各 100 对：

- `match`：硬要求满足，核心能力证据充分；
- `partial_match`：存在关键未知、可迁移能力或可补足差距，不能安全接受或拒绝；
- `nonmatch`：明确不满足硬要求，或乐观上界仍低于阈值。

标注员只能根据冻结岗位规则和简历原文判断，不能查看系统分数。先计算 Cohen's kappa；建议 kappa ≥ 0.80 后冻结裁决标签。主指标是三分类 Accuracy、macro-F1、各类 P/R/F1 和 3×3 混淆矩阵。达标条件为 Accuracy ≥ 0.90。

## 3. 数据文件

### 3.1 简历金标准与预测

金标准和预测都使用 JSONL，每行一个样本。金标准必须包含 `source_text`；预测实体应包含 `evidence_quote`。

```json
{"sample_id":"R001","source_text":"脱敏后的完整简历文本","entities":[{"type":"name","value":"候选人甲","evidence_quote":"姓名：候选人甲"},{"type":"skill","value":"Python","evidence_quote":"使用 Python 完成模型训练"}]}
```

### 3.2 匹配金标准与预测

```json
{"pair_id":"P001","resume_id":"R001","job_id":"J001","label":"partial_match"}
```

预测文件只需：

```json
{"pair_id":"P001","label":"partial_match"}
```

## 4. 运行评测

在 `backend` 目录运行：

```powershell
uv run python tools/evaluate_r_daea_pjf.py `
  --resume-gold data/test/r_daea_pjf/resume_gold.jsonl `
  --resume-predictions data/test/r_daea_pjf/resume_predictions.jsonl `
  --matching-gold data/test/r_daea_pjf/matching_gold.jsonl `
  --matching-predictions data/test/r_daea_pjf/matching_predictions.jsonl `
  --output data/processed/reports/r_daea_pjf_stage1.json
```

DeepSeek Key 只填入 `backend/.env` 的 `APP_LLM_API_KEY`，不要填写或提交到 `.env.example`。模型、Base URL 和超时也在同一文件配置。

## 5. 需要交回的结果

完成第一批实验后，提供：

1. `r_daea_pjf_stage1.json`；
2. 脱敏后的错误样本清单（漏提、错提、标签混淆分别列出）；
3. 使用的 DeepSeek 模型名、提示版本、算法版本；
4. 双人标注一致率和 Cohen's kappa；
5. OCR 软件与版本，以及扫描件失败原因统计。

收到结果后进入下一阶段：误差归因、仅在开发集上校准规则与阈值、冻结 v3，然后进行主动取证对照/消融实验。不得直接在测试集上调参。

## 6. 第二批主动取证实验（第一批完成后再做）

从第一批中的 `partial_match` 和区间跨阈值样本抽取至少 100 对，对比：不提问、按重要度提问、随机合规提问、R-DAEA-PJF 决策价值提问。记录每轮问题、真实答案状态、区间宽度、最终标签和人工裁决。

主要指标：最终准确率、平均问题数、平均区间缩减、安全错误率、转人工率；另做去除稳健项、去除隐私/公平/操纵成本、点分替代区间分的消融实验。
