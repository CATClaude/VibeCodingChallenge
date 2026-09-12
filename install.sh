#!/usr/bin/env bash
set -euo pipefail

DEST="${1:-$HOME/cosyvoice3-4070ti-super}"
mkdir -p "$DEST/output"
cd "$DEST"

for cmd in docker nvidia-smi; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Fehlt: $cmd" >&2; exit 1; }
done

nvidia-smi >/dev/null

echo "Erzeuge CosyVoice3-Dateien in $DEST"

cat > docker-compose.yml <<'YAML'
services:
  cosyvoice:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: cosyvoice3
    restart: unless-stopped
    ports:
      - "8188:8188"
    environment:
      NVIDIA_VISIBLE_DEVICES: "0"
      NVIDIA_DRIVER_CAPABILITIES: "compute,utility"
      MODEL_REPO: "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"
      MODEL_DIR: "/models/Fun-CosyVoice3-0.5B-2512"
      VOICE_ID: "de_thorsten"
      VOICE_DIR: "/voices"
      PORT: "8188"
    volumes:
      - cosyvoice_models:/models
      - cosyvoice_voices:/voices
      - ./output:/output
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["0"]
              capabilities: ["gpu"]
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8188/health"]
      interval: 20s
      timeout: 5s
      retries: 30
      start_period: 180s
volumes:
  cosyvoice_models:
  cosyvoice_voices:
YAML

cat > Dockerfile <<'DOCKER'
FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04
ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    git git-lfs build-essential curl wget ffmpeg unzip sox libsox-dev ca-certificates && \
    rm -rf /var/lib/apt/lists/* && git lfs install
RUN wget -q https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -O /tmp/miniforge.sh && \
    bash /tmp/miniforge.sh -b -p /opt/conda && rm /tmp/miniforge.sh
ENV PATH=/opt/conda/bin:$PATH
RUN conda create -y -n cosyvoice python=3.10 && \
    conda run -n cosyvoice conda install -y -c conda-forge pynini==2.1.5
WORKDIR /workspace
RUN git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
ENV PATH=/opt/conda/envs/cosyvoice/bin:/opt/conda/bin:$PATH
ENV PYTHONPATH=/workspace/CosyVoice:/workspace/CosyVoice/third_party/Matcha-TTS
RUN python -m pip install --no-cache-dir --upgrade \
      'pip<25.2' 'setuptools<81' wheel wheel-stub packaging 'numpy<2' cython && \
    cd /workspace/CosyVoice && \
    pip install --no-cache-dir --no-build-isolation -r requirements.txt && \
    pip install --no-cache-dir fastapi 'uvicorn[standard]' python-multipart huggingface_hub piper-tts
COPY app.py /app/app.py
COPY bootstrap.py /app/bootstrap.py
WORKDIR /app
EXPOSE 8188
ENTRYPOINT ["python", "/app/bootstrap.py"]
DOCKER

cat > bootstrap.py <<'PY'
import os
import subprocess
from pathlib import Path
from huggingface_hub import snapshot_download, hf_hub_download

MODEL_REPO = os.getenv("MODEL_REPO", "FunAudioLLM/Fun-CosyVoice3-0.5B-2512")
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/models/Fun-CosyVoice3-0.5B-2512"))
VOICE_DIR = Path(os.getenv("VOICE_DIR", "/voices"))
VOICE_ID = os.getenv("VOICE_ID", "de_thorsten")
PORT = os.getenv("PORT", "8188")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
VOICE_DIR.mkdir(parents=True, exist_ok=True)
Path("/output").mkdir(parents=True, exist_ok=True)
subprocess.run(["nvidia-smi"], check=True)

if not any(MODEL_DIR.iterdir()):
    snapshot_download(repo_id=MODEL_REPO, local_dir=str(MODEL_DIR), local_dir_use_symlinks=False)

onnx = VOICE_DIR / "de_DE-thorsten-high.onnx"
jsonf = VOICE_DIR / "de_DE-thorsten-high.onnx.json"
if not onnx.exists():
    hf_hub_download("Thorsten-Voice/Piper", "de_DE-thorsten-high.onnx", local_dir=str(VOICE_DIR))
if not jsonf.exists():
    hf_hub_download("Thorsten-Voice/Piper", "de_DE-thorsten-high.onnx.json", local_dir=str(VOICE_DIR))

wav = VOICE_DIR / f"{VOICE_ID}.wav"
txt = VOICE_DIR / f"{VOICE_ID}.txt"
prompt = "Willkommen. Dies ist eine klare und natuerliche deutsche Referenzstimme fuer die lokale Sprachausgabe."
if not wav.exists():
    subprocess.run(["piper", "--model", str(onnx), "--config", str(jsonf), "--output_file", str(wav)], input=prompt.encode("utf-8"), check=True)
txt.write_text(prompt, encoding="utf-8")

os.execvp("uvicorn", ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", PORT])
PY

cat > app.py <<'PY'
import io, os, threading, wave
import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from cosyvoice.cli.cosyvoice import AutoModel

MODEL_DIR = os.getenv("MODEL_DIR", "/models/Fun-CosyVoice3-0.5B-2512")
VOICE_DIR = os.getenv("VOICE_DIR", "/voices")
VOICE_ID = os.getenv("VOICE_ID", "de_thorsten")
PROMPT_PREFIX = "You are a helpful assistant.<|endofprompt|>"
VOICE_WAV = f"{VOICE_DIR}/{VOICE_ID}.wav"
VOICE_TXT = f"{VOICE_DIR}/{VOICE_ID}.txt"

app = FastAPI(title="CosyVoice3")
lock = threading.Lock()
cosyvoice = AutoModel(model_dir=MODEL_DIR)
prompt_text = open(VOICE_TXT, encoding="utf-8").read().strip()
try:
    cosyvoice.add_zero_shot_spk(prompt_text, VOICE_WAV, VOICE_ID)
    cached_voice = True
except Exception:
    cached_voice = False

class SpeechRequest(BaseModel):
    model: str = "cosyvoice3"
    input: str
    voice: str = VOICE_ID
    response_format: str = "wav"
    speed: float = 1.0

@app.get("/health")
def health():
    return {"status": "ok", "model": "cosyvoice3", "voice": VOICE_ID}

@app.get("/v1/models")
def models():
    return {"data": [{"id": "cosyvoice3", "object": "model"}]}

@app.get("/v1/voices")
def voices():
    return {"data": [{"id": VOICE_ID, "language": "de"}]}

@app.post("/v1/audio/speech")
def speech(req: SpeechRequest):
    if req.voice != VOICE_ID:
        raise HTTPException(400, f"Unknown voice: {req.voice}")
    if req.response_format.lower() != "wav":
        raise HTTPException(400, "Only wav is supported")
    if not (0.5 <= req.speed <= 2.0):
        raise HTTPException(400, "speed must be between 0.5 and 2.0")
    text = PROMPT_PREFIX + req.input
    with lock, torch.inference_mode():
        if cached_voice:
            chunks = cosyvoice.inference_zero_shot(text, "", "", zero_shot_spk_id=VOICE_ID, stream=False, speed=req.speed)
        else:
            chunks = cosyvoice.inference_zero_shot(text, prompt_text, VOICE_WAV, stream=False, speed=req.speed)
        audio_parts = []
        sr = 24000
        for out in chunks:
            tensor = out.get("tts_speech")
            sr = int(out.get("sample_rate", sr))
            if tensor is not None:
                audio_parts.append(tensor.detach().float().cpu().reshape(-1))
        if not audio_parts:
            raise HTTPException(500, "No audio generated")
        audio = torch.cat(audio_parts).clamp(-1, 1).numpy()
    pcm = (audio * 32767.0).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm)
    return Response(buf.getvalue(), media_type="audio/wav")
PY

cat > test.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p output
curl -fsS http://127.0.0.1:8188/health
printf '\n'
curl -fsS http://127.0.0.1:8188/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model":"cosyvoice3","voice":"de_thorsten","input":"Hallo. Das ist ein deutscher Test von CosyVoice drei auf der RTX 4070 Ti Super.","response_format":"wav","speed":1.0}' \
  --output output/test-de.wav
ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,sample_rate,channels -of default=noprint_wrappers=1 output/test-de.wav
echo "SUCCESS: $(realpath output/test-de.wav)"
SH
chmod +x test.sh

echo "Baue und starte CosyVoice3..."
docker compose up -d --build

echo
echo "Gestartet. Logs:   cd $DEST && docker compose logs -f"
echo "Health:            http://127.0.0.1:8188/health"
echo "Test:              cd $DEST && ./test.sh"
echo "API:               http://127.0.0.1:8188/v1/audio/speech"
