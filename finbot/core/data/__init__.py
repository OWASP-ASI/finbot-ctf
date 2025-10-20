"""Data layer for the FinBot platform
- Handles database connections, models and operations.
- Uses ORM to be flexible with sql db types
"""

# Import models to ensure they are registered with the declarative base
from . import models  # noqa: F401
