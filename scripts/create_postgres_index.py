import os
from sqlalchemy import create_engine, text
from pathlib import Path

def load_dotenv(dotenv_path: Path):
    env = {}
    if not dotenv_path.exists():
        return env
    with dotenv_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" not in line: continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env

env = os.environ.copy()
env.update(load_dotenv(Path(".env")))

pg_user = env.get("POSTGRES_USER", "admin")
pg_pass = env.get("POSTGRES_PASSWORD", "admin123")
pg_db = env.get("POSTGRES_DB", "lakehouse_db")
pg_host = env.get("POSTGRES_HOST", "localhost")
pg_port = env.get("POSTGRES_PORT", "5435") 

con_str = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
engine = create_engine(con_str, isolation_level="AUTOCOMMIT")

print("=> Đang tạo Mục Lục (Index) trên DB Hồ Chứa... Hệ thống Windows có thể mất từ 2-4 phút để ghi đĩa...")
with engine.connect() as conn:
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_cov_opt_date ON covid_optimized(date)"))
    print("=> Xong Index Ngày Tháng!")
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_cov_opt_sub ON covid_optimized(subregion1_name, subregion2_name)"))
    print("=> Xong Index Các Cấp Tỉnh/Quận!")
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_cov_opt_agg_level ON covid_optimized(aggregation_level)"))
    print("=> Xong Index Cấp Độ Hành Chính (aggregation_level)!")
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_cov_opt_agg_date ON covid_optimized(aggregation_level, date)"))
    print("=> Xong Composite Index (aggregation_level + date) - Siêu tốc!")
print("=> Database đã được TỐI ƯU SIÊU TỐC THÀNH CÔNG!")
