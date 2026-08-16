-- 窗口 A-1 子任务 1.1c:LLM 技术复核的逐词结果(只读 SELECT)
-- 口径:reassessment run 4(llmtech_c1e040de566b6bb586170924)覆盖 run_id=1 的全部
-- 735 条 needs_review。run_id=3(本次审计对象)无 LLM 复核,此导出仅用于评估
-- 「needs_review 交 LLM 复核后的接受率」,为歧义规则效果评估提供参照。
-- 关联说明:复核项通过 technology_match_assessment_id 回溯到 run 1 的评估行,
-- 再经 (job_requirement_id, evidence_span_id) 严格关联取 matched_alias。
SELECT
    lr.reassessment_id,
    lr.technology_match_assessment_id AS assessment_id,
    t.assessment_status_code         AS run1_status_after,
    lr.original_status_code,
    lr.decision_code,
    lr.confidence_score,
    lr.validation_status_code,
    lr.applied,
    lr.reason_code                   AS llm_reason,
    a.normalized_alias,
    req_node.technology_code         AS req_node_code,
    req_node.technology_name         AS req_node_name,
    p.job_title_normalized           AS job_title
FROM biz_llm_technology_reassessment lr
JOIN biz_llm_technology_reassessment_run rr
  ON rr.reassessment_run_id = lr.reassessment_run_id
 AND rr.run_code = 'llmtech_c1e040de566b6bb586170924'
JOIN biz_technology_match_assessment t
  ON t.technology_match_assessment_id = lr.technology_match_assessment_id
JOIN biz_job_requirement r
  ON r.job_requirement_id = t.job_requirement_id
JOIN biz_job_posting p
  ON p.job_posting_id = r.job_posting_id
JOIN md_technology_node req_node
  ON req_node.technology_node_id = r.technology_node_id
JOIN rel_job_requirement_evidence e
  ON e.job_requirement_id = t.job_requirement_id
 AND e.evidence_span_id = t.evidence_span_id
JOIN md_technology_alias a
  ON a.technology_alias_id = e.matched_alias_id
ORDER BY a.normalized_alias, lr.reassessment_id;
