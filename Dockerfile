FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1 \
PORT=8000 \
LANG=C.UTF-8 \
LC_ALL=C.UTF-8 \
PYTHONUTF8=1 \
PIP_NO_CACHE_DIR=1 \
NODE_PATH=/app/node_modules

RUN apt-get update \
&& apt-get install -y --no-install-recommends python3 python3-pip python3-venv build-essential \
&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY package.json package-lock.json ./
RUN npm install

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python3 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
