"""YAML Definition Loader for Challenges and Badges"""

import json
import logging
from pathlib import Path

import yaml
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from finbot.core.data.database import db_session
from finbot.core.data.models import Badge, Challenge
from finbot.ctf.schemas.badge import BadgeSchema
from finbot.ctf.schemas.challenge import ChallengeSchema

logger = logging.getLogger(__name__)


class DefinitionLoader:
    """Loads and syncs challenge/badge definitions from YAML to database"""

    def __init__(self, definitions_path: Path | None = None):
        self.definitions_path = definitions_path or Path(__file__).parent

    def load_all(self, db: Session) -> dict:
        """Load all challenges and badges from YAML files"""
        challenges = self.load_challenges(db)
        badges = self.load_badges(db)
        return {"challenges": challenges, "badges": badges}

    def load_challenges(self, db: Session) -> list[str]:
        """Load all challenge YAML files and upsert to database"""
        challenges_dir = self.definitions_path / "challenges"
        loaded = []

        if not challenges_dir.exists():
            logger.warning("Challenges directory not found: %s", challenges_dir)
            return loaded

        for yaml_file in challenges_dir.rglob("*.yaml"):
            try:
                challenge = self._load_challenge_yaml(yaml_file)
                self._upsert_challenge(db, challenge)
                loaded.append(challenge.id)
                logger.debug("Loaded challenge: %s", challenge.id)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Failed to load challenge from %s: %s", yaml_file, e)

        db.commit()
        return loaded

    def load_badges(self, db: Session) -> list[str]:
        """Load all badge YAML files and upsert to database"""
        badges_dir = self.definitions_path / "badges"
        loaded = []

        if not badges_dir.exists():
            logger.warning("Badges directory not found: %s", badges_dir)
            return loaded

        for yaml_file in badges_dir.rglob("*.yaml"):
            try:
                badge = self._load_badge_yaml(yaml_file)
                self._upsert_badge(db, badge)
                loaded.append(badge.id)
                logger.debug("Loaded badge: %s", badge.id)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Failed to load badge from %s: %s", yaml_file, e)

        db.commit()
        return loaded

    def _load_challenge_yaml(self, path: Path) -> ChallengeSchema:
        """Load and validate a challenge YAML file"""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return ChallengeSchema(**data)

    def _load_badge_yaml(self, path: Path) -> BadgeSchema:
        """Load and validate a badge YAML file"""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return BadgeSchema(**data)

    def _upsert_challenge(self, db: Session, challenge: ChallengeSchema):
        """Insert or update challenge in database (dialect-agnostic)"""
        values = {
            "id": challenge.id,
            "title": challenge.title,
            "description": challenge.description,
            "category": challenge.category,
            "subcategory": challenge.subcategory,
            "difficulty": challenge.difficulty,
            "points": challenge.points,
            "image_url": challenge.image_url,
            "hints": json.dumps([h.model_dump() for h in challenge.hints]),
            "labels": json.dumps(challenge.labels.model_dump()),
            "prerequisites": json.dumps(challenge.prerequisites),
            "resources": json.dumps([r.model_dump() for r in challenge.resources]),
            "detector_class": challenge.detector_class,
            "detector_config": json.dumps(challenge.detector_config)
            if challenge.detector_config
            else None,
            "scoring": json.dumps(challenge.scoring.model_dump())
            if challenge.scoring
            else None,
            "is_active": challenge.is_active,
            "order_index": challenge.order_index,
        }
        self._upsert(db, Challenge, values, "id", preserve_on_update={"is_active"})

    def _upsert_badge(self, db: Session, badge: BadgeSchema):
        """Insert or update badge in database (dialect-agnostic)"""
        values = {
            "id": badge.id,
            "title": badge.title,
            "description": badge.description,
            "category": badge.category,
            "rarity": badge.rarity,
            "points": badge.points,
            "icon_url": badge.icon_url,
            "evaluator_class": badge.evaluator_class,
            "evaluator_config": json.dumps(badge.evaluator_config)
            if badge.evaluator_config
            else None,
            "is_active": badge.is_active,
            "is_secret": badge.is_secret,
        }
        self._upsert(db, Badge, values, "id", preserve_on_update={"is_active"})

    def _upsert(
        self,
        db: Session,
        model,
        values: dict,
        conflict_column: str = "id",
        preserve_on_update: set[str] | None = None,
    ):
        """Dialect-agnostic upsert (INSERT ... ON CONFLICT UPDATE).

        Fields in ``preserve_on_update`` are included in the INSERT (for new
        rows) but excluded from the ON CONFLICT UPDATE set, so existing DB
        values are kept across restarts.
        """
        dialect = db.bind.dialect.name if db.bind else "sqlite"
        skip = {conflict_column} | (preserve_on_update or set())
        update_set = {k: v for k, v in values.items() if k not in skip}

        if dialect == "sqlite":
            stmt = sqlite_insert(model).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[conflict_column],
                set_=update_set,
            )
        elif dialect == "postgresql":
            stmt = pg_insert(model).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[conflict_column],
                set_=update_set,
            )
        else:
            instance = model(**values)
            db.merge(instance)
            return

        db.execute(stmt)


# Singleton instance
_loader: DefinitionLoader | None = None


def get_loader() -> DefinitionLoader:
    """Get singleton loader instance"""
    global _loader  # pylint: disable=global-statement
    if _loader is None:
        _loader = DefinitionLoader()
    return _loader


def load_definitions_on_startup():
    """Load definitions on app startup - call from main.py"""
    loader = get_loader()
    with db_session() as db:
        result = loader.load_all(db)
        logger.info(
            "CTF definitions loaded: %d challenges, %d badges",
            len(result["challenges"]),
            len(result["badges"]),
        )
        return result
