# OWASP FinBot CTF

See Collaborator Hub for details on this project: https://github.com/OWASP-ASI/FinBot-CTF-workstream


## Dev Guide (Temporary)

** Warning: `main` branch is potentially unstable **

Please follow below instructions to test drive the current branch

```bash
# Install dependencies
uv sync

# Setup database
uv run python scripts/setup_database.py

# Start the platform
uv run python run.py
```

Platform runs at http://localhost:8000
