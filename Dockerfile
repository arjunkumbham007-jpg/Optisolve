FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/optisolve

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    python3-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    dvisvgm \
    ghostscript \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install -r /app/requirements.txt

COPY . /app
RUN g++ -std=c++17 -O2 -Wall -Wextra -pedantic \
      solver/main.cpp solver/simplex.cpp solver/json_export.cpp \
      -o solver/optisolve \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin optisolve \
    && mkdir -p /app/runtime/jobs \
    && chown -R optisolve:optisolve /app/runtime /home/optisolve

ENV OPTISOLVE_ENV=production \
    OPTISOLVE_RUNTIME_DIR=/app/runtime

USER optisolve
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()" || exit 1

# One worker is intentional: render semaphore and in-memory rate limits are process-local.
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
