"""
Fix OJM (Outer Join Mismatch): Điền dữ liệu Oxford Policy vào đúng rows epidemiology.
load_covid_data_to_postgres.py tạo ra 2 loại rows riêng biệt cho cùng (date, location_key):
  - Rows epidemiology: new_confirmed!=NULL, school_closing=NULL
  - Rows Oxford:       new_confirmed=NULL,  school_closing!=NULL
Script này UPDATE bằng exact (date, location_key) match.
"""
import os
from sqlalchemy import create_engine, text
from pathlib import Path

def load_dotenv(p: Path):
    env = {}
    if not p.exists(): return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env

env = os.environ.copy()
env.update(load_dotenv(Path(".env")))
con_str = (f"postgresql://{env.get('POSTGRES_USER','admin')}:{env.get('POSTGRES_PASSWORD','admin123')}"
           f"@{env.get('POSTGRES_HOST','localhost')}:{env.get('POSTGRES_PORT','5435')}"
           f"/{env.get('POSTGRES_DB','lakehouse_db')}")
engine = create_engine(con_str, isolation_level="AUTOCOMMIT")

print("=== FIX OUTER JOIN MISMATCH ===")
print("Đang kiểm tra phạm vi ngày của dữ liệu Oxford...")

with engine.connect() as conn:
    # 1. Kiểm tra date range của Oxford rows
    r = conn.execute(text("""
        SELECT MIN(date), MAX(date), COUNT(DISTINCT location_key)
        FROM covid_optimized
        WHERE school_closing IS NOT NULL AND date IS NOT NULL
    """)).fetchone()
    print(f"Oxford date range: {r[0]} → {r[1]}, {r[2]} countries")

    r2 = conn.execute(text("""
        SELECT MIN(date), MAX(date), COUNT(DISTINCT location_key)
        FROM covid_optimized
        WHERE new_confirmed IS NOT NULL AND LENGTH(location_key) <= 2
    """)).fetchone()
    print(f"Epidemiology date range: {r2[0]} → {r2[1]}, {r2[2]} countries")

    # 2. Sample location_keys from Oxford
    sample = conn.execute(text("""
        SELECT DISTINCT location_key FROM covid_optimized
        WHERE school_closing IS NOT NULL LIMIT 10
    """)).fetchall()
    print(f"Sample Oxford location_keys: {[x[0] for x in sample]}")

    # 3. Thử UPDATE với exact date + location_key match
    print("\nĐang chạy UPDATE điền school_closing, workplace_closing, mobility...")
    result = conn.execute(text("""
        UPDATE covid_optimized AS epi
        SET 
            school_closing              = pol.school_closing,
            workplace_closing           = pol.workplace_closing,
            mobility_retail_and_recreation = COALESCE(epi.mobility_retail_and_recreation, pol.mobility_retail_and_recreation)
        FROM (
            SELECT DISTINCT ON (date, location_key)
                date, location_key, school_closing, workplace_closing,
                mobility_retail_and_recreation
            FROM covid_optimized
            WHERE school_closing IS NOT NULL
            ORDER BY date, location_key
        ) pol
        WHERE epi.date = pol.date
          AND epi.location_key = pol.location_key
          AND epi.new_confirmed IS NOT NULL
          AND epi.school_closing IS NULL
    """))
    print(f"UPDATE hoàn thành! Rows đã được điền: {result.rowcount:,}")

    # 4. Kiểm tra kết quả
    r3 = conn.execute(text("""
        SELECT COUNT(*) FROM covid_optimized
        WHERE LENGTH(location_key) <= 2
          AND new_confirmed IS NOT NULL
          AND school_closing IS NOT NULL
    """)).fetchone()
    print(f"\nKiểm tra sau UPDATE — Overlap rows: {r3[0]:,}")

    if r3[0] == 0:
        print("\n⚠️  UPDATE không fix được — dates không khớp giữa Oxford và Epidemiology!")
        print("Cần kiểm tra thêm định dạng ngày tháng trong 2 nguồn dữ liệu.")
    else:
        print(f"\n✅ SUCCESS! {r3[0]:,} rows giờ có ĐẦY ĐỦ cả new_confirmed VÀ school_closing!")
        print("Pipeline ML Policy có thể chạy ngay với dữ liệu chính xác!")
