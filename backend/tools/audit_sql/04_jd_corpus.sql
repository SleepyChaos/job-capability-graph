-- 窗口 A-1 子任务 1.2:run 3 覆盖的全部 JD 正文 + 证据标记(只读 SELECT)
-- 口径:rel_job_parse_result 中 run_code = 'jdparse_e7328e6370fbee62e79d2098' 的全部岗位
-- (含零证据 JD),accepted/needs_review 计数与去重技术点数按 run 3 评估计。
-- 用途:L3 覆盖盲区的高频未识别技术词抽取语料。
SELECT
    p.job_posting_id,
    p.job_title_normalized,
    p.job_title_raw,
    p.job_level_code,
    p.region_text,
    pr.parse_status_code,
    pr.parse_quality_score,
    COALESCE(ev.accepted_cnt, 0)      AS accepted_cnt,
    COALESCE(ev.review_cnt, 0)        AS review_cnt,
    COALESCE(ev.distinct_node_cnt, 0) AS distinct_node_cnt,
    p.jd_clean_text
FROM rel_job_parse_result pr
JOIN biz_job_parse_run run
  ON run.job_parse_run_id = pr.job_parse_run_id
 AND run.run_code = 'jdparse_e7328e6370fbee62e79d2098'
JOIN biz_job_posting p
  ON p.job_posting_id = pr.job_posting_id
LEFT JOIN (
    SELECT r.job_posting_id,
           SUM(t.assessment_status_code = 'accepted')      AS accepted_cnt,
           SUM(t.assessment_status_code = 'needs_review')  AS review_cnt,
           COUNT(DISTINCT r.technology_node_id)            AS distinct_node_cnt
    FROM biz_technology_match_assessment t
    JOIN biz_job_requirement r
      ON r.job_requirement_id = t.job_requirement_id
    WHERE t.job_parse_run_id = (
        SELECT job_parse_run_id FROM biz_job_parse_run
        WHERE run_code = 'jdparse_e7328e6370fbee62e79d2098'
    )
    GROUP BY r.job_posting_id
) ev ON ev.job_posting_id = pr.job_posting_id
ORDER BY p.job_posting_id;
