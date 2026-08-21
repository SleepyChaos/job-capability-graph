"""Probe Splink v4 API to find correct method names for u-estimation/predict/cluster."""
import duckdb
import pandas as pd
import splink
from splink import DuckDBAPI, SettingsCreator
from splink.comparison_library import JaroWinklerAtThresholds, LevenshteinAtThresholds

df = pd.DataFrame({
    "rec_id": ["a", "b", "c", "d"],
    "org_id": ["ORG1", "ORG1", "ORG2", "ORG3"],
    "name": ["宇树科技", "宇树科技股份有限公司", "智元机器人", "星动纪元"],
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

print("=== dir(linker) ===")
for a in sorted(dir(linker)):
    if not a.startswith("_"):
        print("  ", a)

print("=== linker.training? ===")
print("has training attr:", hasattr(linker, "training"))
if hasattr(linker, "training"):
    print("  training methods:", [a for a in sorted(dir(linker.training)) if not a.startswith("_")])

print("=== linker.estimate_u options ===")
for name in ["estimate_u_using_random_sampling", "estimate_u", "estimate_probability_two_random_records_match"]:
    print("  ", name, "->", hasattr(linker, name))

print("=== linker.inference? ===")
print("has inference attr:", hasattr(linker, "inference"))
if hasattr(linker, "inference"):
    print("  inference methods:", [a for a in sorted(dir(linker.inference)) if not a.startswith("_")])

print("=== linker.clustering? ===")
print("has clustering attr:", hasattr(linker, "clustering"))
if hasattr(linker, "clustering"):
    print("  clustering methods:", [a for a in sorted(dir(linker.clustering)) if not a.startswith("_")])

print("=== linker.predict? ===")
print("has predict attr:", hasattr(linker, "predict"))

print("=== settings methods ===")
print("has settings attr:", hasattr(linker, "settings"))
print("settings dict keys:", list(linker.settings.as_dict().keys()) if hasattr(linker, "settings") else "N/A")
