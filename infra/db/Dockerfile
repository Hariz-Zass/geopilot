FROM postgis/postgis:16-3.5

ARG PGVECTOR_VERSION=0.8.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        postgresql-server-dev-16 \
    && curl -fsSL "https://github.com/pgvector/pgvector/archive/refs/tags/v${PGVECTOR_VERSION}.tar.gz" -o /tmp/pgvector.tar.gz \
    && mkdir -p /tmp/pgvector \
    && tar -xzf /tmp/pgvector.tar.gz -C /tmp/pgvector --strip-components=1 \
    && make -C /tmp/pgvector \
    && make -C /tmp/pgvector install \
    && rm -rf /tmp/pgvector /tmp/pgvector.tar.gz \
    && apt-get purge -y --auto-remove build-essential curl postgresql-server-dev-16 \
    && rm -rf /var/lib/apt/lists/*
