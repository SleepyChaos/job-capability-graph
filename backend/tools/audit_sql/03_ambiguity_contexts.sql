-- 窗口 A-1 子任务 1.1c:歧义规则评估的语境证据(只读 SELECT)
-- 口径:run_code = 'jdparse_e7328e6370fbee62e79d2098'(run_id=3)。
-- 用途:检查「语境命中 80 分被 accepted」的样本里,语境词与命中词是否真正相关
-- (正向语境词可能在段落任意位置出现,与命中词无句法关联)。
SELECT
    t.technology_match_assessment_id AS assessment_id,
    r.job_posting_id,
    p.job_title_normalized           AS job_title,
    t.assessment_status_code        AS status,
    t.reason_code,
    a.normalized_alias,
    req_node.technology_code        AS req_node_code,
    req_node.technology_name        AS req_node_name,
    ctx.evidence_text               AS context_text
FROM biz_technology_match_assessment t
JOIN biz_job_parse_run pr
  ON pr.job_parse_run_id = t.job_parse_run_id
 AND pr.run_code = 'jdparse_e7328e6370fbee62e79d2098'
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
LEFT JOIN biz_evidence_span ctx
  ON ctx.evidence_span_id = t.context_evidence_span_id
WHERE t.ambiguity_rule_id IS NOT NULL
ORDER BY a.normalized_alias, t.assessment_status_code, t.technology_match_assessment_id;
