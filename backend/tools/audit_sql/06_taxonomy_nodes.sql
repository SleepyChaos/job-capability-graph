-- 窗口 A-1 子任务 1.2:词表节点全量清单(只读 SELECT)
-- 口径:taxonomy v1.1(taxonomy_version_id=1),与 run 3 使用的词表相同。
-- 用途:L1/L2 父节点名称(候选新增技术点的挂载建议)、层级规模核对。
SELECT
    n.technology_node_id,
    n.technology_code,
    n.level_code,
    n.technology_name,
    p.technology_code  AS parent_code,
    p.technology_name  AS parent_name,
    p.level_code       AS parent_level
FROM md_technology_node n
LEFT JOIN md_technology_node p
  ON p.technology_node_id = n.parent_technology_node_id
WHERE n.taxonomy_version_id = 1
ORDER BY n.technology_code;
