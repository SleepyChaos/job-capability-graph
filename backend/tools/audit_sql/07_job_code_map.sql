-- 窗口 A-1 子任务 1.3a:job_code -> job_posting_id 映射(只读 SELECT)
-- 用途:标注候选清单(build_jd_annotation_batch.py 输出 job_code)与
-- 语料快照(04 号,按 job_posting_id)之间的确定性关联。
SELECT job_code, job_posting_id
FROM biz_job_posting
ORDER BY job_posting_id;
