"""Pytest setup: force offline mode so tests never call Gemini and run in under a minute."""
import os  # environment variables
import sys  # module search path
from pathlib import Path  # paths

os.environ["SPRINTS_OFFLINE"] = "1"  # deterministic offline stand-in for the LLM and embedder
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `import src` work from any cwd

from src.tools.db_queries import DB_PATH, build_database  # DB builder

if not DB_PATH.exists():  # make sure the SQLite file exists before tests run
    build_database()
