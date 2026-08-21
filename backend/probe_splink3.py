"""Test Splink v4 dedupe quality with u-estimation + p2rrm, inspect match_probs and clusters."""
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
linker.training.estimate_u_using_random_sampling(max_pairs=1e5)
# estimate probability_two_random_records_match via EM on one comparison while deactivating the other
try:
    linker.training.estimate_parameters_using_expectation_maximisation(
        "l.name = r.name", comparisons_to_deactivate=["name"])
    print("[ok] EM p2rrm done")
except Exception as e:
    print("[warn] EM failed:", repr(e))

predictions = linker.inference.predict(threshold_match_weight=-8)
pdf = predictions.as_pandas_dataframe()
print("predict columns:", list(pdf.columns))
print(pdf[["rec_id_l", "rec_id_r", "match_probability"]].to_string())

clusters = linker.clustering.cluster_pairwise_predictions_at_threshold(predictions, 0.9)
cdf = clusters.as_pandas_dataframe()
print("cluster columns:", list(cdf.columns))
print(cdf.to_string())
