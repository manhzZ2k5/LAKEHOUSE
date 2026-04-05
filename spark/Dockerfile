FROM apache/spark:3.5.1

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        libbz2-dev \
        libffi-dev \
        liblzma-dev \
        libncursesw5-dev \
        libreadline-dev \
        libsqlite3-dev \
        libssl-dev \
        llvm \
        tk-dev \
        xz-utils \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYENV_ROOT=/opt/pyenv
ENV PATH=${PYENV_ROOT}/bin:${PYENV_ROOT}/shims:${PATH}
ARG PYTHON_VERSION=3.10.14
ARG DELTA_VERSION=3.2.0
ARG HADOOP_AWS_VERSION=3.3.4
ARG AWS_SDK_VERSION=1.12.262
ARG SCALA_BINARY_VERSION=2.12

RUN git clone --depth 1 https://github.com/pyenv/pyenv.git ${PYENV_ROOT} \
    && ${PYENV_ROOT}/bin/pyenv install -s ${PYTHON_VERSION} \
    && ${PYENV_ROOT}/bin/pyenv global ${PYTHON_VERSION} \
    && ${PYENV_ROOT}/bin/pyenv rehash

RUN set -eux; \
    curl -fSL "https://repo1.maven.org/maven2/io/delta/delta-spark_${SCALA_BINARY_VERSION}/${DELTA_VERSION}/delta-spark_${SCALA_BINARY_VERSION}-${DELTA_VERSION}.jar" -o "/opt/spark/jars/delta-spark_${SCALA_BINARY_VERSION}-${DELTA_VERSION}.jar"; \
    curl -fSL "https://repo1.maven.org/maven2/io/delta/delta-storage/${DELTA_VERSION}/delta-storage-${DELTA_VERSION}.jar" -o "/opt/spark/jars/delta-storage-${DELTA_VERSION}.jar"; \
    curl -fSL "https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_AWS_VERSION}/hadoop-aws-${HADOOP_AWS_VERSION}.jar" -o "/opt/spark/jars/hadoop-aws-${HADOOP_AWS_VERSION}.jar"; \
    curl -fSL "https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar" -o "/opt/spark/jars/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar"

ENV PYSPARK_PYTHON=/opt/pyenv/shims/python
ENV PYSPARK_DRIVER_PYTHON=/opt/pyenv/shims/python

USER spark
