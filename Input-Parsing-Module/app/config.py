from pathlib import Path

from dotenv import load_dotenv


def load_environment() -> None:
    """Load environment variables from the project-level .env file if present."""

    project_root =   Path(__file__).resolve().parent.parent
    env_path= project_root / ".env"

    load_dotenv(dotenv_path=env_path, override=False)
