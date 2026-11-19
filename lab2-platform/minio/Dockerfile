FROM debian:bookworm-slim
ARG MINIO_RELEASE=RELEASE.2025-04-22T22-12-26Z
# Docker Hub removed the upstream image; pin the official release binary by SHA-256.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://github.com/minio/minio/releases/download/${MINIO_RELEASE}/minio.linux-amd64.${MINIO_RELEASE}" -o /usr/local/bin/minio \
    && echo '53e2a2cb16c5366ea6fbbc479c19ddb4c6a0948273e752f740fb1fbf27bb817c  /usr/local/bin/minio' | sha256sum -c - \
    && chmod 0755 /usr/local/bin/minio \
    && useradd --uid 10001 --create-home minio \
    && mkdir /data && chown minio:minio /data
USER 10001:10001
EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data"]
