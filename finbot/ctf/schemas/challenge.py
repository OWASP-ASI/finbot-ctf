"""CTF Challenge Schemas"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class HintSchema(BaseModel):
    """Hint Schema  with point cost"""

    cost: int = Field(ge=0, le=100, description="Cost in points to use the hint")
    text: str = Field(min_length=1, description="Hint text")


class ResourceSchema(BaseModel):
    """External Learning Resource"""

    title: str = Field(min_length=1, description="Resource title")
    url: str = Field(min_length=1, description="Resource URL")


class LabelsSchema(BaseModel):
    """Security framework labels"""

    owasp_llm: list[str] = Field(default_factory=list)
    cwe: list[str] = Field(default_factory=list)
    mitre_atlas: list[str] = Field(default_factory=list)
    owasp_agentic: list[str] = Field(default_factory=list)


class ScoringModifierSchema(BaseModel):
    """A single scoring modifier (penalty or bonus) applied on challenge completion"""

    type: str = Field(min_length=1, max_length=50, description="Modifier type (e.g. 'pi_jb')")
    penalty: float = Field(
        ge=0.0, le=1.0, default=0.0, description="Penalty fraction (0.5 = lose 50%)"
    )
    min_confidence: float = Field(
        ge=0.0, le=1.0, default=0.5, description="Minimum confidence to trigger"
    )
    judge_system_prompt: str | None = Field(
        default=None, description="Custom judge prompt override"
    )
    model: str | None = Field(default=None, description="Specific LLM model for the modifier judge")


class ScoringSchema(BaseModel):
    """Scoring configuration for a challenge"""

    modifiers: list[ScoringModifierSchema] = Field(
        default_factory=list, description="Ordered list of scoring modifiers"
    )


class ChallengeSchema(BaseModel):
    """Validates challenge YAML structure"""

    id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$",
        min_length=1,
        max_length=64,
        description="Unique challenge identifier (lowercase, hyphens allowed)",
    )
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10)

    category: str = Field(min_length=2, max_length=50)
    subcategory: str | None = Field(default=None, max_length=50)
    difficulty: Literal["beginner", "intermediate", "advanced", "expert"]
    points: int = Field(ge=0, le=1000, default=100)

    image_url: str | None = Field(default=None, max_length=1000)
    hints: list[HintSchema] = Field(default_factory=list)
    labels: LabelsSchema = Field(default_factory=LabelsSchema)
    prerequisites: list[str] = Field(default_factory=list)
    resources: list[ResourceSchema] = Field(default_factory=list)

    detector_class: str = Field(min_length=1, max_length=100)
    detector_config: dict | None = Field(default=None)

    scoring: ScoringSchema | None = Field(default=None, description="Scoring modifiers config")

    is_active: bool = True
    order_index: int = Field(ge=0, default=0)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate challenge ID"""

        if v.startswith("-") or v.endswith("-"):
            raise ValueError("ID cannot start or end with hyphen")
        return v
