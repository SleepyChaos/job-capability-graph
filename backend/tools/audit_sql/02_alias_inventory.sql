-- 窗口 A-1 子任务 1.1:全量别名清单(只读 SELECT)
-- 口径:当前 active 词表(taxonomy v1.1,与 run 3 使用的 taxonomy_version_id=1 相同)。
-- 用途:命中为 0 的别名(反向问题)、别名长度分布、别名挂载层级核对。
SELECT
    a.technology_alias_id   AS alias_id,
    a.alias_text,
    a.normalized_alias,
    CHAR_LENGTH(a.alias_text) AS alias_len,
    a.is_matchable,
    a.alias_type_code,
    a.source_type_code,
    n.level_code            AS node_level,
    n.technology_code       AS node_code,
    n.technology_name       AS node_name,
    l3.technology_code      AS l3_code,
    l3.technology_name      AS l3_name
FROM md_technology_alias a
JOIN md_technology_node n
  ON n.technology_node_id = a.technology_node_id
LEFT JOIN md_technology_node l3
  ON l3.technology_node_id = n.parent_technology_node_id
ORDER BY a.technology_alias_id;
