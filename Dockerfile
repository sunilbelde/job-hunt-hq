# --- Stage 1: fetch a pinned, checksum-verified tectonic binary for the target arch ---
FROM python:3.12-slim AS tectonic
ARG TARGETARCH
ARG TECTONIC_VERSION=0.15.0
ARG SHA256_AMD64=dfb82876f2986862996e564fa507a9e576e0c1e3bee63c2c1bd677c2543e6407
ARG SHA256_ARM64=1f59f9fb8eb65e8ba18658fc9016767e7d3e12488ded8b8fffa34254e51ce42c
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) arch=x86_64; sha="$SHA256_AMD64" ;; \
      arm64) arch=aarch64; sha="$SHA256_ARM64" ;; \
      *) echo "unsupported arch: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/tectonic.tgz \
      "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-${arch}-unknown-linux-musl.tar.gz"; \
    echo "${sha}  /tmp/tectonic.tgz" | sha256sum -c -; \
    tar -xzf /tmp/tectonic.tgz -C /usr/local/bin tectonic

# --- Stage 2: runtime image ---
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TECTONIC_CACHE_DIR=/opt/tectonic-cache

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=tectonic /usr/local/bin/tectonic /usr/local/bin/tectonic
COPY app ./app
COPY data ./data

RUN useradd --system --uid 10001 --create-home appuser \
    && mkdir -p "$TECTONIC_CACHE_DIR" \
    && chown appuser "$TECTONIC_CACHE_DIR"
USER appuser

# Warm tectonic's package/font cache at build time (needs network here) so that
# rendering works offline at request time. Also fails the build if the template
# does not compile.
RUN python -c "from app.rendering import render_pdf; assert render_pdf().startswith(b'%PDF')"

# Cloud Run injects PORT; default for local runs.
ENV PORT=8080
CMD exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port "${PORT}"
