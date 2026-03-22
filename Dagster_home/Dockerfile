FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jre-headless && \
    rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

WORKDIR /opt/dagster/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dagster.yaml /opt/dagster/dagster_home/
ENV DAGSTER_HOME=/opt/dagster/dagster_home
COPY . .
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "4000"]
