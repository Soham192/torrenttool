import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

QBIT_HOST = os.environ.get("QBIT_HOST", "localhost")
QBIT_PORT = int(os.environ.get("QBIT_PORT", "8080"))
QBIT_USERNAME = os.environ.get("QBIT_USERNAME", "admin")
QBIT_PASSWORD = os.environ.get("QBIT_PASSWORD", "")
DEFAULT_SAVE_PATH = os.environ.get("DEFAULT_SAVE_PATH", "/downloads")
