FROM python:3.10-slim-bookworm

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        openjdk-17-jre-headless && \
    rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"
ARG DELTA_VERSION=3.2.0
ARG HADOOP_AWS_VERSION=3.3.4
ARG AWS_SDK_VERSION=1.12.262
ARG SCALA_BINARY_VERSION=2.12

WORKDIR /opt/dagster/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN set -eux; \
    mkdir -p /opt/dagster/jars; \
    curl -fSL "https://repo1.maven.org/maven2/io/delta/delta-spark_${SCALA_BINARY_VERSION}/${DELTA_VERSION}/delta-spark_${SCALA_BINARY_VERSION}-${DELTA_VERSION}.jar" -o "/opt/dagster/jars/delta-spark_${SCALA_BINARY_VERSION}-${DELTA_VERSION}.jar"; \
    curl -fSL "https://repo1.maven.org/maven2/io/delta/delta-storage/${DELTA_VERSION}/delta-storage-${DELTA_VERSION}.jar" -o "/opt/dagster/jars/delta-storage-${DELTA_VERSION}.jar"; \
    curl -fSL "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar" -o "/opt/dagster/jars/hadoop-aws-${HADOOP_AWS_VERSION}.jar"; \
    curl -fSL "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar" -o "/opt/dagster/jars/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar"
COPY dagster.yaml /opt/dagster/dagster_home/
ENV DAGSTER_HOME=/opt/dagster/dagster_home
COPY . .
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "4000"]
