"""
Check Prerequisites

Detects which tools and services are available on this machine,
then summarizes which deployment paths are feasible.

Audience: Core setup — run before first install.

Usage:
    python scripts/check_prerequisites.py
"""

import io
import shutil
import subprocess
import sys

# Ensure stdout can handle Unicode on all platforms (Windows cp1252 fix)
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def check_python() -> tuple[bool, str]:
    """Check Python >= 3.13."""
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= (3, 13):
        return True, version_str
    return False, version_str


def check_command(name: str) -> bool:
    """Check if a command is on PATH."""
    return shutil.which(name) is not None


def check_redis() -> bool:
    """Check if Redis is reachable via redis-cli ping."""
    if not check_command("redis-cli"):
        return False
    try:
        result = subprocess.run(
            ["redis-cli", "ping"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        return result.returncode == 0 and "PONG" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_postgres() -> bool:
    """Check if psql is available."""
    return check_command("psql")


def check_docker() -> bool:
    """Check if Docker daemon is running."""
    if not check_command("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=False,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def main():
    print("Checking prerequisites...\n")

    py_ok, py_ver = check_python()
    uv_ok = check_command("uv")
    redis_ok = check_redis()
    pg_ok = check_postgres()
    docker_ok = check_docker()

    status = lambda ok: "✅" if ok else "❌"

    print(f"  Python 3.13+   {status(py_ok)}  {py_ver}")
    print(f"  uv             {status(uv_ok)}  {'installed' if uv_ok else 'not found'}")
    print(f"  Redis          {status(redis_ok)}  {'running' if redis_ok else 'not available'}")
    print(f"  PostgreSQL     {status(pg_ok)}  {'available' if pg_ok else 'not found'}")
    print(f"  Docker         {status(docker_ok)}  {'running' if docker_ok else 'not available'}")

    # Feasibility
    docker_ready = docker_ok
    local_base = py_ok and uv_ok
    sqlite_ready = local_base and redis_ok
    pg_ready = local_base and redis_ok and pg_ok

    any_feasible = docker_ready or sqlite_ready

    print("\n" + "=" * 55)
    print("  What you can run")
    print("=" * 55)
    print(f"  Docker Compose (quickest)         {status(docker_ready)}  {'Ready' if docker_ready else 'Docker not available'}")
    print(f"  Local + SQLite (minimal)          {status(sqlite_ready)}  {'Ready' if sqlite_ready else 'missing: ' + ', '.join(
        name for ok, name in [(py_ok, 'Python 3.13+'), (uv_ok, 'uv'), (redis_ok, 'Redis')] if not ok
    )}")
    print(f"  Local + PostgreSQL (recommended)  {status(pg_ready)}  {'Ready' if pg_ready else 'missing: ' + ', '.join(
        name for ok, name in [(py_ok, 'Python 3.13+'), (uv_ok, 'uv'), (redis_ok, 'Redis'), (pg_ok, 'PostgreSQL')] if not ok
    )}")

    if not redis_ok and local_base:
        print("\n  ⚠️  Without Redis the platform starts but CTF challenge detection won't work.")

    if any_feasible:
        print("\nNext steps:")
        if docker_ready:
            print("  cp .env.example .env             # configure environment")
            print("  docker compose up                # Docker path")
        if sqlite_ready:
            if docker_ready:
                print("  -- or --")
            print("  uv sync                          # Local path")
            print("  uv run python scripts/db.py setup")
            print("  uv run python run.py")
        print()

    sys.exit(0 if any_feasible else 1)


if __name__ == "__main__":
    main()
