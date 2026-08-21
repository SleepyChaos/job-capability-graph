"""Probe how to set m_probability priors on v4 comparison levels, then verify dedupe works."""
import duckdb
import pandas as pd
import splink
from splink import DuckDBAPI, SettingsCreator
from splink.comparison_library import JaroWinklerAtThresholds, LevenshteinAtThresholds

df = pd.DataFrame({
    "rec_id": ["a", "b", "c", "d", "e", "f", "g"],
    "org_id": ["O1", "O1", "O2", "O3", "O3", "O4", "O5"],
    "name": ["宇树科技", "宇树科技股份有限公司", "智元机器人", "星动纪元", "星动纪元科技",
             "银河通用", "千寻智能"],
})

con = duckdb.connect(":memory:")
con.register("input_data", df)

# Build comparison and inspect levels
c1 = JaroWinklerAtThresholds("name", [0.9, 0.8])
print("=== JaroWinkler levels ===")
for i, lvl in enumerate(c1.comparison_levels):
    print(f"  [{i}] {lvl.label}  m_probability={getattr(lvl,'m_probability',None)}  u_probability={getattr(lvl,'u_probability',None)}")

# Set m priors
m_priors = [0.95, 0.85, 0.4, 0.01]  # exact, jw>=0.9, jw>=0.8, else
for i, lvl in enumerate(c1.comparison_levels):
    if i < len(m_priors):
        lvl.m_probability = m_priors[i]

settings = SettingsCreator(
    link_type="dedupe_only",
    unique_id_column_name="rec_id",
    probability_two_random_records_match=0.001,
    comparisons=[
        c1,
        LevenshteinAtThresholds("name", [2, 4]),
    ],
    blocking_rules_to_generate_predictions=[
        "l.name = r.name",
        "substr(l.name,1,3) = substr(r.name,1,3)",
    ],
)

linker = splink.Linker("input_data", settings, db_api=DuckDBAPI(con))
linker.training.estimate_u_using_random_sampling(max_pairs=1e5)

predictions = linker.inference.predict(threshold_match_weight=-8)
pdf = predictions.as_pandas_dataframe()
print("predict columns:", list(pdf.columns))
print(pdf[["rec_id_l", "rec_id_r", "match_probability"]].to_string())

clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(predictions, 0.9)
cdf = clusters.as_pandas_dataframe()
print("cluster columns:", list(cdf.columns))
print(cdf[["cluster_id", "rec_id", "org_id", "name"]].to_string())
