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

con_str = f"postgresql://{env.get('POSTGRES_USER', 'admin')}:{env.get('POSTGRES_PASSWORD', 'admin123')}@{env.get('POSTGRES_HOST', 'localhost')}:{env.get('POSTGRES_PORT', '5435')}/{env.get('POSTGRES_DB', 'lakehouse_db')}"
engine = create_engine(con_str, isolation_level="AUTOCOMMIT")

print("Tạo Composite Index (aggregation_level + date)...")
print("Đây là index QUAN TRỌNG NHẤT - có thể mất 3-5 phút lần đầu. Xin kiên nhẫn...")

with engine.connect() as conn:
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_cov_agg_date 
        ON covid_optimized(aggregation_level, date)
    """))

print("HOÀN THÀNH! Dagster giờ sẽ query trong vài mili-giây!")
