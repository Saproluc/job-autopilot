"""
utils.py — Utility helpers for Job AutoPilot.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from rich.logging import RichHandler


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load and validate user configuration."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Run from the project root directory."
        )
    
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    
    # Validate required fields
    required = ["personal.full_name", "personal.email", "job_search.titles"]
    for field in required:
        parts = field.split(".")
        val = cfg
        for p in parts:
            val = val.get(p) if isinstance(val, dict) else None
        if not val:
            raise ValueError(f"Missing required config field: {field}")
    
    return cfg


def setup_logging(log_dir: str = "output/logs") -> logging.Logger:
    """Configure rich logging to console + file."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    log_file = Path(log_dir) / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(rich_tracebacks=True, show_path=False),
            logging.FileHandler(log_file, encoding="utf-8"),
        ]
    )
    
    # Silence noisy third-party loggers
    for lib in ["httpx", "httpcore", "playwright", "asyncio"]:
        logging.getLogger(lib).setLevel(logging.WARNING)
    
    return logging.getLogger("job_autopilot")


def notify_done(count: int, cfg: dict):
    """
    Optional SMS notification via Twilio when run completes.
    Requires TWILIO_* env vars to be set.
    """
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_phone = os.environ.get("TWILIO_FROM_PHONE")
    to_phone = os.environ.get("TWILIO_TO_PHONE")
    
    if not all([twilio_sid, twilio_token, from_phone, to_phone]):
        return
    
    try:
        from twilio.rest import Client
        client = Client(twilio_sid, twilio_token)
        client.messages.create(
            body=f"✅ Job AutoPilot: {count} applications filled and waiting for your review. Check your Chrome tabs!",
            from_=from_phone,
            to=to_phone
        )
    except ImportError:
        pass  # Twilio not installed
    except Exception as e:
        logging.getLogger("job_autopilot").warning(f"SMS notification failed: {e}")
