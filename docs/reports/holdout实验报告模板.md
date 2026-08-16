# 留出重发现实验报告

> 协议版本:{{protocol_version}}
> 生成工具:`backend/tools/run_holdout_experiment.py`(本模板位于
> `docs/reports/holdout实验报告模板.md`;报告由脚本按实验记录确定性渲染,
> 同一实验记录得到逐字节相同的报告,不含时间戳)。

## 解读边界(先读这一段)

- 本实验验证「技术结构 → 岗位」的推断能力:**随机遮蔽部分正式岗位,在遮蔽状态下
  跑新岗位推演,检查被遮蔽岗位能否作为高分候选被重新发现**。不使用时间轴。
- 正式执行的前提是**任务组 5(下游重新标定)完成**;抽取质量修复之前跑出的数字
  没有研究意义,不得作为论文结论引用。
- 推演调用完全复用 `run_discovery`(automatic 模式),本实验不改动 discovery 的
  评分、分类与去重逻辑;被遮蔽岗位通过 `excluded_role_ids` 参数在覆盖率、novelty
  与最近岗位分类全链路中被当作不存在。

## 1. 冻结字段(实验身份)

| 字段 | 值 |
| --- | --- |
| run_code | `{{run_code}}` |
| target_date | {{target_date}} |
| mask_ratio(遮蔽比例) | {{mask_ratio}} |
| seed(随机种子) | {{seed}} |
| 算法版本 | {{algorithm_version}} |
| input_snapshot_hash | `{{input_snapshot_hash}}` |
| 遮蔽资格线(min_technology_count) | {{min_technology_count}} |
| 重新发现判定门槛(Jaccard) | {{jaccard_threshold}} |
| Recall@K 的 K | 10 / 25 / 50 / 100 |
| 命中重放缓存 | {{already_completed}} |

同输入 + 同 seed + 同参数 → 同遮蔽集、同指标。任何影响推演输出的输入变化都会
改变 input_snapshot_hash 并触发新运行。

## 2. 参数快照(run.parameter_json)

```json
{{parameters_json}}
```

## 3. 遮蔽集概要

- 资格岗位(生效版本技术词 ≥ {{min_technology_count}}):{{eligible_role_count}} 个
- 本次遮蔽:**{{masked_role_count}}** 个(比例 {{mask_ratio}},种子 {{seed}})
- 遮蔽集由(合格岗位集合 + mask_ratio + seed)确定性导出,完整 role_id 清单见
  审计文件 `holdout_manifest_{{run_code}}.json`,其 `manifest_sha256` 字段为
  manifest 内容的自校验哈希。

## 4. Recall@K 与随机排序基线

被遮蔽岗位计为「重新发现」的条件:存在候选与其技术集合的 Jaccard ≥
{{jaccard_threshold}},且该候选按 candidate_score 降序排名进入前 K。
分母为全部被遮蔽岗位。随机基线用同一候选集合、同一匹配判定,仅将排名替换为
同种子({{seed}})的随机洗牌。

{{recall_table}}

## 5. 排名分布与逐岗位明细

排名摘要:{{rank_summary}}

{{per_role_table}}

## 6. 技术集合 Jaccard 分布

被遮蔽岗位与其最佳候选的技术集合 Jaccard:{{jaccard_summary}}

## 7. 审计文件

| 文件 | 内容 |
| --- | --- |
| `holdout_manifest_{{run_code}}.json` | 冻结字段 + 遮蔽集 + 参数快照 + 自校验 sha256 |
| `holdout_metrics_{{run_code}}.json` | 冻结字段 + 全部指标(含逐岗位明细) |
| `holdout实验报告_{{run_code}}.md` | 本报告 |
