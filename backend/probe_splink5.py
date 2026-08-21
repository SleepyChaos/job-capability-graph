"""Fully-prior-informed Splink v4 model (m + u set), verify dedupe clusters correctly."""
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

c1 = JaroWinklerAtThresholds("name", [0.9, 0.8])
c1.m_probabilities = [0.97, 0.85, 0.4, 0.01]
c1.u_probabilities = [0.01, 0.04, 0.10, 0.85]

c2 = LevenshteinAtThresholds("name", [2, 4])
c2.m_probabilities = [0.95, 0.8, 0.4, 0.01]
c2.u_probabilities = [0.02, 0.05, 0.12, 0.81]

settings = SettingsCreator(
    link_type="dedupe_only",
    unique_id_column_name="rec_id",
    probability_two_random_records_match=0.001,
    comparisons=[c1, c2],
    blocking_rules_to_generate_predictions=[
        "l.name = r.name",
        "substr(l.name,1,3) = substr(r.name,1,3)",
    ],
)

linker = splink.Linker("input_data", settings, db_api=DuckDBAPI(con))
predictions = linker.inference.predict(threshold_match_weight=-8)
pdf = predictions.as_pandas_dataframe()
print("predict columns:", list(pdf.columns))
print(pdf[["rec_id_l", "rec_id_r", "match_probability"]].to_string())

clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(predictions, 0.9)
cdf = clusters.as_pandas_dataframe()
print("cluster columns:", list(cdf.columns))
print(cdf[["cluster_id", "rec_id", "org_id", "name"]].to_string())
