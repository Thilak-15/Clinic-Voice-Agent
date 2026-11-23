"""Runtime configuration, read from environment variables (.env)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
# "Sarah", one of ElevenLabs' default voices. Any voice id from your library works.
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID") or "EXAVITQu4vr4xnSDxMaL"
ELEVENLABS_TTS_MODEL = os.getenv("ELEVENLABS_TTS_MODEL") or "eleven_flash_v2_5"

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL") or "gemini-3.6-flash"

CLINIC_NAME = os.getenv("CLINIC_NAME") or "Sunrise Health Clinic"
AGENT_NAME = os.getenv("AGENT_NAME") or "Maya"
CLINIC_TIMEZONE = os.getenv("CLINIC_TIMEZONE") or "Asia/Kolkata"

DB_PATH = Path(os.getenv("DB_PATH") or ROOT / "data" / "clinic.db")

HOST = os.getenv("HOST") or "0.0.0.0"
PORT = int(os.getenv("PORT") or 7860)
CORS_ORIGINS = [o.strip() for o in (os.getenv("CORS_ORIGINS") or "*").split(",") if o.strip()]
