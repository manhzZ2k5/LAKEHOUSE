FROM python:3.10-slim

WORKDIR opt/dagster/app
copy requirements.txt .
run pip install --no-cache-dir -r requirements.txt
copy dagster.yaml /opt/dagster/dagster_home/
env DAGSTER_HOME=/opt/dagster/dagster_home
copy . .
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "4000"]
