"""
Fix Population Merge: Điền dữ liệu demographics (population, age groups) vào
đúng rows epidemiology trong bảng covid_optimized.

Vấn đề (giống fix_policy_merge.py):
  - Rows epidemiology: new_confirmed != NULL, population = NULL
  - Rows demographics: new_confirmed = NULL,  population != NULL
  Kết quả: Silver Lake có population = 0 toàn bộ → incidence_rate = 0 → ML vô nghĩa.

Giải pháp:
  Population là hằng số theo quốc gia (không đổi theo ngày).
  → UPDATE epidemiology rows bằng cách lấy population từ bất kỳ demographics row nào
    có cùng location_key (không cần khớp date).
"""
import os
from sqlalchemy import create_engine, text
from pathlib import Path


def load_dotenv(p: Path):
    env = {}
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


env = os.environ.copy()
env.update(load_dotenv(Path(".env")))
con_str = (
    f"postgresql://{env.get('POSTGRES_USER','postgres_user')}:{env.get('POSTGRES_PASSWORD','admin123')}"
    f"@{env.get('POSTGRES_HOST','localhost')}:{env.get('POSTGRES_PORT','5435')}"
    f"/{env.get('POSTGRES_DB','dagster_db')}"
)
engine = create_engine(con_str, isolation_level="AUTOCOMMIT")

print("=== FIX POPULATION MERGE ===\n")

with engine.connect() as conn:

    # 1. Kiểm tra có rows demographics không
    r = conn.execute(text("""
        SELECT COUNT(DISTINCT location_key), MIN(population), MAX(population)
        FROM covid_optimized
        WHERE population IS NOT NULL AND population > 0
          AND LENGTH(location_key) <= 2
    """)).fetchone()
    print(f"Demographics rows (country-level): {r[0]:,} countries | pop range {r[1]:,} → {r[2]:,}")

    if r[0] == 0:
        print("\n⚠️  Không tìm thấy rows nào có population > 0!")
        print("Kiểm tra xem data demographics đã được load vào covid_optimized chưa.")

        # Kiểm tra toàn bộ table
        r2 = conn.execute(text("""
            SELECT COUNT(*), COUNT(population), COUNT(new_confirmed)
            FROM covid_optimized
            WHERE LENGTH(location_key) <= 2
        """)).fetchone()
        print(f"Country rows total: {r2[0]:,} | pop not null: {r2[1]:,} | confirmed not null: {r2[2]:,}")
        exit(0)

    # 2. Kiểm tra trước khi UPDATE
    r2 = conn.execute(text("""
        SELECT COUNT(*) FROM covid_optimized
        WHERE LENGTH(location_key) <= 2
          AND new_confirmed IS NOT NULL
          AND population IS NULL
    """)).fetchone()
    print(f"Epidemiology rows cần điền population: {r2[0]:,}")

    if r2[0] == 0:
        print("\n✅ Không cần fix — population đã được điền đầy đủ!")
        exit(0)

    # 3. UPDATE: điền population vào epidemiology rows
    # Population là hằng số per location_key → dùng MAX() để lấy giá trị đại diện
    print("\nĐang chạy UPDATE điền population, age groups...")
    result = conn.execute(text("""
        UPDATE covid_optimized AS epi
        SET
            population                        = demo.population,
            population_density                = demo.population_density,
            population_male                   = demo.population_male,
            population_female                 = demo.population_female,
            population_age_60_69              = demo.population_age_60_69,
            population_age_70_79              = demo.population_age_70_79,
            population_age_80_and_older       = demo.population_age_80_and_older,
            gdp_per_capita_usd                = demo.gdp_per_capita_usd,
            human_development_index           = demo.human_development_index,
            life_expectancy                   = demo.life_expectancy,
            hospital_beds_per_1000            = demo.hospital_beds_per_1000
        FROM (
            SELECT DISTINCT ON (location_key)
                location_key,
                population,
                population_density,
                population_male,
                population_female,
                population_age_60_69,
                population_age_70_79,
                population_age_80_and_older,
                gdp_per_capita_usd,
                human_development_index,
                life_expectancy,
                hospital_beds_per_1000
            FROM covid_optimized
            WHERE population IS NOT NULL AND population > 0
              AND LENGTH(location_key) <= 2
            ORDER BY location_key
        ) demo
        WHERE epi.location_key = demo.location_key
          AND epi.new_confirmed IS NOT NULL
          AND epi.population IS NULL
    """))
    print(f"UPDATE hoàn thành! Rows đã được điền: {result.rowcount:,}")

    # 4. Kiểm tra kết quả
    r3 = conn.execute(text("""
        SELECT
            COUNT(*) as total_epi,
            COUNT(population) as has_population,
            ROUND(AVG(population)::numeric, 0) as avg_population
        FROM covid_optimized
        WHERE LENGTH(location_key) <= 2
          AND new_confirmed IS NOT NULL
    """)).fetchone()
    print(f"\nSau UPDATE:")
    print(f"  Epidemiology rows: {r3[0]:,}")
    print(f"  Rows có population: {r3[1]:,}")
    print(f"  Population trung bình: {r3[2]:,}")

    if r3[1] == r3[0]:
        print("\n✅ SUCCESS! Tất cả epidemiology rows đã có population.")
        print("Bước tiếp theo: Re-run Silver Lake asset trong Dagster để cập nhật data.")
    else:
        still_missing = r3[0] - r3[1]
        print(f"\n⚠️  Còn {still_missing:,} rows chưa có population.")
        print("Có thể do những countries chỉ có epidemiology data, không có demographics rows.")
