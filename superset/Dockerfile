FROM apache/superset:latest

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    libsasl2-dev libldap2-dev libssl-dev \
    libkrb5-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "pyhive[hive]" thrift thrift_sasl sasl

USER superset
