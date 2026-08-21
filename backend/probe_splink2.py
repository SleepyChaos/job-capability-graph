"""Full Splink v4 flow probe: train -> predict -> cluster; inspect output columns."""
import duckdb
import pandas as pd
import splink
from splink import DuckDBAPI, SettingsCreator
from splink.comparison_library import JaroWinklerAtThresholds, LevenshteinAtThresholds

df = pd.DataFrame({
    "rec_id": ["a", "b", "c", "d", "e"],
    "org_id": ["ORG1", "ORG1", "ORG2", "ORG3", "ORG3"],
    "name": ["宇树科技", "宇树科技股份有限公司", "智元机器人", "星动纪元", "星动纪元科技"],
})

con = duckdb.connect(":memory:")
con.register("input_data", df)

settings = SettingsCreator(
    link_type="dedupe_only",
    unique_id_column_name="rec_id",
    comparisons=[
        JaroWinklerAtThresholds("name", [0.9, 0.8]),
        LevenshteinAtThresholds("name", [2, 4]),
    ],
    blocking_rules_to_generate_predictions=[
        "l.name = r.name",
        "substr(l.name,1,3) = substr(r.name,1,3)",
    ],
)

linker = splink.Linker("input_data", settings, db_api=DuckDBAPI(con))

# u-estimation
linker.training.estimate_u_using_random_sampling(max_pairs=1e5)
print("[ok] estimate_u_using_random_sampling done")

# predict
predictions = linker.inference.predict(threshold_match_weight=-8)
print("[ok] predict done")
pdf = predictions.as_pandas_dataframe()
print("predict columns:", list(pdf.columns))
print(pdf[["unique_id_l", "unique_id_r", "match_probability"]].to_string())

# cluster
clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(predictions, 0.9)
cdf = clusters.as_pandas_dataframe()
print("cluster columns:", list(cdf.columns))
print(cdf.to_string())
