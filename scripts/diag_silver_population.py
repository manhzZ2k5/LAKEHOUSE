"""
Script chẩn đoán: kiểm tra tại sao incidence_rate = 0 trong Silver Lake.
Chạy bằng: docker exec lakehouse-dagster-webserver python3 /opt/dagster/app/diag_silver_population.py
"""
from deltalake import DeltaTable
import pandas as pd
import numpy as np

opts = {
    "AWS_ACCESS_KEY_ID":          "minio_admin",
    "AWS_SECRET_ACCESS_KEY":      "minio_secret_secure_password_123",
    "AWS_ENDPOINT_URL":           "http://minio:9000",
    "AWS_ALLOW_HTTP":             "true",
    "AWS_REGION":                 "us-east-1",
}

print("Đang đọc Silver Lake...")
dt = DeltaTable("s3://silver-lake/covid_cleaned/", storage_options=opts)
df = dt.to_pyarrow_table(
    columns=["date", "location_key", "new_confirmed", "population", "subregion1_name"]
).to_pandas()

# Filter country-level
df = df[df["subregion1_name"].isna()].copy()
df = df[df["new_confirmed"] > 0]

print("\n=== KIỂM TRA POPULATION ===")
print(f"Tổng rows (country, confirmed>0): {len(df):,}")
print(f"population = null : {df['population'].isna().sum():,}  ({df['population'].isna().mean()*100:.1f}%)")
print(f"population = 0    : {(df['population']==0).sum():,}  ({(df['population']==0).mean()*100:.1f}%)")
print(f"population > 0    : {df['population'].gt(0).sum():,}  ({df['population'].gt(0).mean()*100:.1f}%)")

pop = df["population"].replace(0, np.nan)
df["incidence_rate"] = (df["new_confirmed"] / pop * 100_000).fillna(0)

print("\n=== KIỂM TRA INCIDENCE_RATE ===")
print(f"incidence_rate = 0 : {(df['incidence_rate']==0).sum():,}  ({(df['incidence_rate']==0).mean()*100:.1f}%)")
print(f"incidence_rate mean: {df['incidence_rate'].mean():.6f}")
print(f"incidence_rate std : {df['incidence_rate'].std():.6f}")
print(f"incidence_rate max : {df['incidence_rate'].max():.6f}")

print("\n=== KIỂM TRA DUPLICATE ===")
dupes = df.duplicated(subset=["date", "location_key"]).sum()
print(f"Duplicate (date, location_key): {dupes:,}")

print("\n=== 5 DÒNG MẪU ===")
print(df[["date","location_key","new_confirmed","population","incidence_rate"]].head(10).to_string())
