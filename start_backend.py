#!/usr/bin/env python3
"""
PrimeData Backend Server Startup Script
Platform-agnostic script that works on Windows, macOS, and Linux
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def find_venv():
    """Find virtual environment directory."""
    current_dir = Path.cwd()
    
    # Try .venv first, then venv
    for venv_name in [".venv", "venv"]:
        venv_path = current_dir / venv_name
        if venv_path.exists():
            return venv_path
    
    return None

def get_python_executable(venv_path=None):
    """Get Python executable path."""
    if venv_path:
        system = platform.system()
        if system == "Windows":
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            python_exe = venv_path / "bin" / "python"
        
        if python_exe.exists():
            return str(python_exe)
    
    # Fall back to system Python
    return sys.executable

def main():
    """Main function to start the backend server."""
    print("Starting PrimeData backend server...")
    print(f"Platform: {platform.system()} {platform.release()}")
    print()
    
    # Find virtual environment
    venv_path = find_venv()
    if venv_path:
        print(f"Found virtual environment: {venv_path}")
    else:
        print("Warning: Virtual environment not found.")
        print("Using system Python. It's recommended to use a virtual environment:")
        print("  python -m venv venv")
        print()
    
    # Get Python executable
    python_exe = get_python_executable(venv_path)
    print(f"Using Python: {python_exe}")
    print()
    
    # Navigate to backend directory
    backend_dir = Path(__file__).parent / "backend"
    if not backend_dir.exists():
        print(f"Error: Backend directory not found: {backend_dir}")
        sys.exit(1)
    
    os.chdir(backend_dir)
    print(f"Working directory: {os.getcwd()}")
    print()
    
    # Set PYTHONPATH
    src_path = backend_dir / "src"
    pythonpath = str(src_path)
    
    # Get existing PYTHONPATH if any
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    if existing_pythonpath:
        pythonpath = f"{pythonpath}{os.pathsep}{existing_pythonpath}"
    
    os.environ["PYTHONPATH"] = pythonpath
    print(f"PYTHONPATH set to: {pythonpath}")
    print()
    
    # Start the FastAPI server
    print("Starting backend server...")
    print("=" * 60)
    print()
    
    try:
        # Run uvicorn
        cmd = [
            python_exe,
            "-m", "uvicorn",
            "src.primedata.api.app:app",
            "--reload",
            "--host", "0.0.0.0",
            "--port", "8000"
        ]
        
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("Backend server stopped by user.")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print(f"\nError: Backend server failed to start (exit code {e.returncode})")
        sys.exit(1)
    except FileNotFoundError:
        print(f"\nError: Python executable not found: {python_exe}")
        print("Please ensure Python is installed and virtual environment is set up correctly.")
        sys.exit(1)

if __name__ == "__main__":
    main()







