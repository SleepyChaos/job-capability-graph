# 测试数据模板与样例

本目录为《测试数据集设计方案 v1》的可执行配套资产。每类数据均包含：

- `templates/`：字段模板，复制后填写；
- `examples/`：一份完整的合成样例，用于理解字段和联调读取器。

所有样例均为合成内容，不代表真实企业、岗位、求职者或正式研究结论。

## 文件对照

| 类型 | 模板 | 样例 |
| --- | --- | --- |
| 数据集清单 | `templates/dataset_manifest.template.yaml` | `examples/dataset_manifest.example.yaml` |
| 来源与证据 | `templates/source_material.template.json` | `examples/source_material.example.json` |
| JD 解析金标准 | `templates/jd_parsing.template.json` | `examples/jd_parsing.example.json` |
| 简历解析金标准 | `templates/resume_parsing.template.json` | `examples/resume_parsing.example.json` |
| 人岗匹配金标准 | `templates/job_matching.template.json` | `examples/job_matching.example.json` |
| 新岗位闭环场景 | `templates/emerging_job_scenario.template.yaml` | `examples/emerging_job_scenario.example.yaml` |
| 既有岗位更新场景 | `templates/existing_job_evolution.template.yaml` | `examples/existing_job_evolution.example.yaml` |
| 图谱与45天时序 | `templates/graph_timeseries.template.csv` | `examples/graph_timeseries.example.csv` |
| 治理/幻觉/安全样本 | `templates/governance_adversarial.template.yaml` | `examples/governance_adversarial.example.yaml` |
| 工程测试夹具 | `templates/engineering_fixture.template.yaml` | `examples/engineering_fixture.example.yaml` |
| 性能合成数据规格 | `templates/performance_dataset.template.yaml` | `examples/performance_dataset.example.yaml` |
| 通用测试用例 | `templates/test_case.template.yaml` | `examples/test_case.example.yaml` |

## 使用规则

1. 正式样本使用稳定 ID，不在 ID 或文件名中写真实姓名；
2. `template` 文件只定义字段，不进入准确率统计；
3. `example` 文件只用于联调，不进入最终冻结测试集；
4. 正式数据必须绑定数据版本、技术词版本和 SHA-256；
5. 金标准必须由人工标注并完成复核或裁决；
6. 任何技能、职责、匹配理由和新岗位结论都应保存证据；
7. 合成数据、真实数据、受限数据和性能数据必须分开标记。

