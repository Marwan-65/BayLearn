"""Main entry point for running BayLearn applications."""

import sys
import subprocess
from pathlib import Path


def run_ui():
    """Run the Streamlit UI application."""
    ui_path = Path(__file__).parent / "src" / "baylearn" / "ui" / "app.py"
    print(f"Starting BayLearn UI from {ui_path}...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ui_path)])


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
  ui       - Run Streamlit UI
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
