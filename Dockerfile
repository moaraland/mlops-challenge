FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/moaraland/mlops-challenge"

WORKDIR /workspace

# Variáveis de ambiente
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WRAPT_DISABLE_EXTENSIONS=1
ENV TFDS_DATA_DIR=/tfds

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    git \
    libgomp1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- CORREÇÃO AQUI ---
# 1. Copiamos APENAS o requirements primeiro
COPY requirements.txt /workspace/requirements.txt

# 2. Agora o pip consegue encontrar o arquivo para instalar
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 3. Por fim, copiamos o restante do código
COPY . /workspace

EXPOSE 8000

CMD ["bash"]