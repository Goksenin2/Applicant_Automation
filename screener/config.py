"""Load config.yaml and the .env secrets."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str = "config.yaml") -> dict:
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if Path(path).is_absolute() else ROOT / path
    if not cfg_path.exists():
        raise SystemExit(f"{cfg_path} not found. Copy config.example.yaml to config.yaml and fill it in.")
    return yaml.safe_load(cfg_path.read_text())


def monday_token() -> str:
    load_dotenv(ROOT / ".env")
    token = os.environ.get("MONDAY_API_TOKEN")
    if not token:
        raise SystemExit("MONDAY_API_TOKEN is not set (put it in .env).")
    return token
