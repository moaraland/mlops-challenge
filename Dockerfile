# Imagem base para rodar as peças de ML do desafio.
# Nota: usar Python 3.11 ajuda a evitar incompatibilidades do TF/Keras em alguns ambientes.
FROM python:3.11-slim

WORKDIR /workspace

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WRAPT_DISABLE_EXTENSIONS=1 \
    TFDS_DATA_DIR=/tfds


RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /workspace/requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r /workspace/requirements.txt

COPY . /workspace

EXPOSE 8000
CMD ["bash"]
