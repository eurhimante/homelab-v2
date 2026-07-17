FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    ca-certificates \
    libopengl0 \
    libglu1-mesa \
    libwebkit2gtk-4.1-0 \
    libjavascriptcoregtk-4.1-0 \
    libsm6 \
    libmspack0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip3 install --break-system-packages \
    --no-cache-dir \
    -r requirements.txt

COPY . .

COPY orcaslicer /opt/orcaslicer

RUN chmod +x /opt/orcaslicer/bin/orca-slicer \
    && mkdir -p \
        /app/jobs \
        /app/templates_3mf

ENV ORCASLICER_PATH=/opt/orcaslicer/bin/orca-slicer

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
