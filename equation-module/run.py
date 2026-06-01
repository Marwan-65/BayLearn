"""Main entry point for running BayLearn applications."""

import sys
import subprocess
import shutil
from pathlib import Path


def run_ui():
    """Run the React TypeScript UI and API for local development."""
    root = Path(__file__).parent
    frontend_dir = root / "src" / "baylearn-frontend"

    print("Starting BayLearn API on http://127.0.0.1:8000 ...")
    api_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "baylearn.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=root,
    )

    try:
        print("Starting BayLearn React UI on http://127.0.0.1:5173 ...")
        npm_executable = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm_executable:
            raise RuntimeError(
                "npm was not found on PATH. Install Node.js and ensure npm is available, "
                "then run this command again."
            )
        subprocess.run([npm_executable, "run", "dev"], cwd=frontend_dir, check=False)
    finally:
        api_process.terminate()


def run_api():
    """Run the FastAPI server."""
    print("Starting BayLearn API server...")
    subprocess.run([
        sys.executable,
        "-m",
        "uvicorn",
        "baylearn.api:app",
        "--reload"
    ])


def run_example():
    """Run basic usage examples."""
    example_path = Path(__file__).parent / "examples" / "basic_usage.py"
    print(f"Running examples from {example_path}...")
    subprocess.run([sys.executable, str(example_path)])


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("""
Usage: python run.py [command]

Commands:
  ui       - Run React UI + local API
  api      - Run FastAPI server
  example  - Run basic usage examples
  help     - Show this help message
        """)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "ui":
        run_ui()
    elif command == "api":
        run_api()
    elif command == "example":
        run_example()
    elif command == "help":
        main()
    else:
        print(f"Unknown command: {command}")
        main()


if __name__ == "__main__":
    main()
