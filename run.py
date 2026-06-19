#!/usr/bin/env python3

"""
AIRDops Development/Production Wrapper Script

Simplified version that uses .env.local files

"""

import os
import sys
import subprocess
import platform
import time
from pathlib import Path
from typing import Optional


class Colors:
    """ANSI color codes for terminal output."""

    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print formatted header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.OKCYAN}ℹ️  {text}{Colors.ENDC}")


def check_docker() -> bool:
    """Check if Docker is installed and running."""
    try:
        subprocess.run(['docker', '--version'], 
                      capture_output=True, text=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("Docker is not installed or not in PATH")
        print_info("Install Docker from: https://docs.docker.com/get-docker/")
        return False


def get_docker_compose_cmd() -> str:
    """Get the Docker Compose command (v2 or v1)."""
    try:
        subprocess.run(['docker', 'compose', 'version'], 
                      capture_output=True, check=True)
        return 'docker compose'
    except:
        return 'docker-compose'


def check_env_files(mode: str) -> bool:
    """Check if required .env.local files exist."""
    root_dir = Path(__file__).parent
    backend_env = root_dir / "backend" / ".env.local"
    infra_env = root_dir / "infra" / ".env.local"
    
    missing = []
    if not backend_env.exists():
        missing.append(f"backend/.env.local")
    if not infra_env.exists():
        missing.append(f"infra/.env.local")
    
    if missing:
        print_warning(f"Missing .env.local files: {', '.join(missing)}")
        print_info("Create these files based on env.example files")
        return False
    
    print_success("All .env.local files found")
    return True


def start_docker_services(mode: str) -> bool:
    """Start Docker services using docker-compose."""
    print_header("Starting Docker Services")
    
    root_dir = Path(__file__).parent
    infra_dir = root_dir / "infra"
    compose_file = infra_dir / f"docker-compose{'.prod' if mode == 'prod' else ''}.yml"
    env_file = infra_dir / ".env.local"
    
    if not compose_file.exists():
        print_error(f"Docker Compose file not found: {compose_file}")
        return False
    
    docker_cmd = get_docker_compose_cmd()
    
    # Build and start services
    cmd = [
        *docker_cmd.split(),
        "-f", str(compose_file),
    ]
    
    # Add --env-file if .env.local exists, otherwise docker-compose will use .env
    if env_file.exists():
        cmd.extend(["--env-file", str(env_file)])
    
    cmd.extend(["up", "-d", "--build"])
    
    print_info(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, cwd=infra_dir, check=True)
        print_success("Docker services started")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to start Docker services: {e}")
        return False


def run_migrations() -> bool:
    """Run database migrations."""
    print_header("Running Database Migrations")
    
    root_dir = Path(__file__).parent
    backend_dir = root_dir / "backend"
    
    # Find Python executable
    venv_path = find_venv()
    python_exe = get_python_executable(venv_path)
    
    cmd = [python_exe, "-m", "alembic", "upgrade", "head"]
    
    print_info(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, cwd=backend_dir, check=True)
        print_success("Migrations completed")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Migrations failed: {e}")
        return False


def find_venv() -> Optional[Path]:
    """Find virtual environment."""
    current_dir = Path.cwd()
    for venv_name in [".venv", "venv"]:
        venv_path = current_dir / venv_name
        if venv_path.exists():
            return venv_path
    return None


def get_python_executable(venv_path: Optional[Path] = None) -> str:
    """Get Python executable path."""
    if venv_path:
        system = platform.system()
        if system == "Windows":
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            python_exe = venv_path / "bin" / "python"
        
        if python_exe.exists():
            return str(python_exe)
    
    return sys.executable


def start_backend(mode: str):
    """Start backend server."""
    print_header("Starting Backend Server")
    print_info("Backend will start on http://localhost:8000")
    print_info("Press Ctrl+C to stop")
    print()
    
    root_dir = Path(__file__).parent
    backend_dir = root_dir / "backend"
    
    venv_path = find_venv()
    python_exe = get_python_executable(venv_path)
    
    # Set PYTHONPATH
    src_path = backend_dir / "src"
    pythonpath = str(src_path)
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    if existing_pythonpath:
        pythonpath = f"{pythonpath}{os.pathsep}{existing_pythonpath}"
    os.environ["PYTHONPATH"] = pythonpath
    
    cmd = [
        python_exe,
        "-m", "uvicorn",
        "src.primedata.api.app:app",
        "--reload" if mode == "dev" else "",
        "--host", "0.0.0.0",
        "--port", "8000"
    ]
    cmd = [c for c in cmd if c]  # Remove empty strings
    
    try:
        subprocess.run(cmd, cwd=backend_dir, check=True)
    except KeyboardInterrupt:
        print("\n" + "="*60)
        print_success("Shutting down...")
    except subprocess.CalledProcessError as e:
        print_error(f"Backend failed to start: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="AIRDops Development/Production Wrapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py dev              # Start in development mode
  python run.py dev --services-only    # Only start Docker services
  python run.py dev --skip-docker      # Skip Docker (already running)
  python run.py dev --skip-migrations  # Skip database migrations
  python run.py prod             # Start in production mode
        """
    )
    parser.add_argument("mode", choices=["dev", "prod"], 
                       help="Run mode: dev or prod")
    parser.add_argument("--skip-docker", action="store_true", 
                       help="Skip starting Docker services")
    parser.add_argument("--skip-migrations", action="store_true", 
                       help="Skip database migrations")
    parser.add_argument("--services-only", action="store_true", 
                       help="Only start Docker services, don't start backend")
    
    args = parser.parse_args()
    
    print_header(f"AIRDops - {args.mode.upper()} Mode")
    
    # Check prerequisites
    if not check_docker():
        sys.exit(1)
    
    # Check .env.local files
    if not check_env_files(args.mode):
        print_warning("Continuing anyway... (make sure your .env.local files are configured)")
    
    # Start Docker services
    if not args.skip_docker:
        if not start_docker_services(args.mode):
            print_error("Failed to start Docker services")
            sys.exit(1)
    
    if args.services_only:
        print_success("Docker services started. Exiting.")
        return
    
    # Run migrations
    if not args.skip_migrations:
        print_info("Waiting for database to be ready...")
        time.sleep(5)
        
        if not run_migrations():
            print_warning("Migrations failed, but continuing...")
    
    # Start backend
    start_backend(args.mode)


if __name__ == "__main__":
    main()




