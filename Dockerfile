# tiny — Strands agent image for Reachy Mini (Pollen Robotics).
#
# Unlike neon (G1) this image is LIGHT: no CycloneDDS, no librealsense build.
# The Reachy Mini daemon owns the hardware and exposes an HTTP/WS API on :8000.
# These containers are just agent personas (voice / telegram / thinker) that
# connect to that daemon over the network.
#
# Targets:
#   - Reachy Mini Lite:      daemon on the host laptop  → REACHY_HOST=host.docker.internal or localhost (host net)
#   - Reachy Mini Wireless:  daemon on the CM4          → REACHY_HOST=reachy-mini.local (or run on-CM4 with host net)
#   - Simulation:            REACHY_USE_SIM=1           → MuJoCo, no hardware
#
# Canonical entrypoint is the Makefile:
#   make build       # docker compose build
#   make up          # docker compose up -d
#   make logs / make exec / make down

FROM python:3.12-slim

# System deps: audio (PyAudio/portaudio), GL for opencv, gstreamer for SDK media,
# git+build for any source installs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl ca-certificates pkg-config \
    libasound2-dev libportaudio2 portaudio19-dev \
    libgl1 libglib2.0-0 \
    libgirepository1.0-dev gir1.2-gstreamer-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (cache-friendly)
COPY requirements.txt requirements-robot.txt ./
RUN pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt \
 && pip install --no-cache-dir -r requirements-robot.txt || true

# App code
COPY . .

ENV PYTHONUNBUFFERED=1 \
    REACHY_HOST=reachy-mini.local \
    REACHY_PORT=8000 \
    REACHY_CONNECTION_MODE=auto \
    DEVDUCK_AUTO_START_SERVERS=false

# Default entrypoint: REPL agent. Override per-service in docker-compose.
ENTRYPOINT ["python", "agent.py"]
