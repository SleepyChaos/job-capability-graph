-- 窗口 A-1 子任务 1.1:逐评估行的别名命中明细(只读 SELECT)
-- 口径:run_code = 'jdparse_e7328e6370fbee62e79d2098'(run_id=3),无 LLM 回写。
-- 关联链:assessment -> evidence(同 job_requirement_id + evidence_span_id,严格 1:1)-> alias。
-- 注意:rel_job_requirement_evidence 跨 run 累积,禁止只按 job_requirement_id 关联
-- (会膨胀到 2 万+ 行),必须同时限定 evidence_span_id。
SELECT
    t.technology_match_assessment_id AS assessment_id,
    r.job_posting_id,
    r.job_requirement_id            AS requirement_id,
    t.assessment_status_code        AS status,
    t.reason_code,
    t.adjusted_support_score        AS score,
    t.feature_weight,
    t.ambiguity_rule_id,
    r.raw_term,
    r.mention_count,
    r.mapping_method_code,
    req_node.technology_code        AS req_node_code,
    req_node.technology_name        AS req_node_name,
    es.evidence_text                AS span_text,
    a.technology_alias_id           AS alias_id,
    a.alias_text,
    a.normalized_alias,
    a.is_matchable,
    a.alias_type_code,
    alias_node.technology_code      AS alias_node_code,
    alias_node.technology_name      AS alias_node_name,
    alias_l3.technology_code        AS alias_l3_code,
    alias_l3.technology_name        AS alias_l3_name
FROM biz_technology_match_assessment t
JOIN biz_job_parse_run pr
  ON pr.job_parse_run_id = t.job_parse_run_id
 AND pr.run_code = 'jdparse_e7328e6370fbee62e79d2098'
JOIN biz_job_requirement r
  ON r.job_requirement_id = t.job_requirement_id
JOIN md_technology_node req_node
  ON req_node.technology_node_id = r.technology_node_id
JOIN rel_job_requirement_evidence e
  ON e.job_requirement_id = t.job_requirement_id
 AND e.evidence_span_id = t.evidence_span_id
JOIN md_technology_alias a
  ON a.technology_alias_id = e.matched_alias_id
JOIN md_technology_node alias_node
  ON alias_node.technology_node_id = a.technology_node_id
LEFT JOIN md_technology_node alias_l3
  ON alias_l3.technology_node_id = alias_node.parent_technology_node_id
JOIN biz_evidence_span es
  ON es.evidence_span_id = t.evidence_span_id
ORDER BY t.technology_match_assessment_id;
