FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/moaraland/mlops-challenge"

WORKDIR /workspace

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WRAPT_DISABLE_EXTENSIONS=1
ENV TFDS_DATA_DIR=/tfds

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    git \
    libgomp1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . /workspace

EXPOSE 8000

CMD ["bash"]
