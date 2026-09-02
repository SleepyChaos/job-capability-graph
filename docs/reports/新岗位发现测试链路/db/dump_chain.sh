set -e
DB=job_capability_graph
MYSQL="mysql -uroot -proot_password_change_me -N --default-character-set=utf8mb4 $DB"
DUMP="mysqldump -uroot -proot_password_change_me --default-character-set=utf8mb4 --skip-add-drop-table --no-tablespaces --compact --complete-insert $DB"

RUNS="'upstream_9be390dbc3d24c49940931','milestone_efd1667e2c0f4fa3afb7d'"
RUN_IDS=$($MYSQL -e "SELECT GROUP_CONCAT(discovery_run_id) FROM biz_role_discovery_run WHERE run_code IN ($RUNS)")
CAND_IDS=$($MYSQL -e "SELECT GROUP_CONCAT(emerging_role_candidate_id) FROM biz_emerging_role_candidate WHERE discovery_run_id IN ($RUN_IDS)")
ROLE_IDS=$($MYSQL -e "SELECT GROUP_CONCAT(DISTINCT approved_job_role_id) FROM biz_emerging_role_candidate WHERE emerging_role_candidate_id IN ($CAND_IDS) AND approved_job_role_id IS NOT NULL")
MS_IDS=$($MYSQL -e "SELECT GROUP_CONCAT(milestone_event_id) FROM biz_milestone_event WHERE milestone_code = 'MS-917aad10d0da45789999'")
NODE_IDS=$($MYSQL -e "SELECT GROUP_CONCAT(technology_node_id) FROM md_technology_node WHERE technology_code IN ('T1.01.11','T1.09.01','T1.02.10','T3.08.04','T1.02')")

echo "-- 新岗位发现测试链路 · 数据库样例"
echo "-- 覆盖两次推演运行（upstream_gap / milestone_gap）产出的全部候选及其证据、审核与入库记录。"
echo "-- 生成方式见同目录 export_test_chain.py 与本文件顶部的筛选条件。"
echo "SET NAMES utf8mb4;"
$DUMP --where="discovery_run_id IN ($RUN_IDS)" biz_role_discovery_run 2>/dev/null || true
$DUMP --where="discovery_run_id IN ($RUN_IDS)" biz_emerging_role_candidate
$DUMP --where="emerging_role_candidate_id IN ($CAND_IDS)" rel_candidate_technology biz_candidate_score_component biz_standard_job_description
$DUMP --where="queue_code='job_discovery' AND target_type_code='emerging_role' AND target_id IN ($CAND_IDS)" biz_review_task
$DUMP --where="job_role_id IN ($ROLE_IDS)" biz_job_role
$DUMP --where="milestone_event_id IN ($MS_IDS)" biz_milestone_event rel_milestone_technology rel_milestone_evidence
$DUMP --where="technology_node_id IN ($NODE_IDS)" md_technology_node md_technology_alias
