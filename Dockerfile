FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

#libcairo is needed by cairosvg, which is used to convert animated stickers
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
#deltachat2[full] installs the deltachat-rpc-server binary, which the bot needs
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . ./
RUN chmod +x ./start.sh

CMD ["./start.sh"]
