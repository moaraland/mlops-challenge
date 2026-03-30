FROM n8nio/n8n:1.40.0

USER root

SHELL ["/bin/sh", "-lc"]

RUN if command -v apk >/dev/null 2>&1; then \
      apk add --no-cache bash curl git python3 py3-pip docker-cli docker-cli-compose docker-compose; \
    elif command -v apt-get >/dev/null 2>&1; then \
      apt-get update && apt-get install -y --no-install-recommends \
        bash \
        curl \
        git \
        python3 \
        python3-pip \
        docker.io \
        docker-compose && \
      rm -rf /var/lib/apt/lists/*; \
    else \
      echo "Unsupported base image: no known package manager found." >&2; \
      exit 1; \
    fi

RUN if [ ! -x /usr/bin/docker ]; then \
      echo "Docker CLI binary not found after package installation." >&2; \
      exit 1; \
    fi && \
    mv /usr/bin/docker /usr/bin/docker-real

COPY n8n/docker-wrapper.sh /usr/local/bin/docker

RUN chmod +x /usr/local/bin/docker

USER root
