from pathlib import Path

from dotenv import load_dotenv

# Local runs read the repo-root .env; in Docker, compose injects the variables.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
