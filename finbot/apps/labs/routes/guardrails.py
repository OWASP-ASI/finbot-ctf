"""FinBot Labs — Guardrail webhook configuration API."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.repositories import (
    CTFEventRepository,
    LabsGuardrailConfigRepository,
)
from finbot.guardrails.schemas import HookKind
from finbot.guardrails.service import GuardrailHookService

router = APIRouter(prefix="/api/v1/guardrails", tags=["labs-guardrails"])


# -- Request / response schemas --


class GuardrailConfigRequest(BaseModel):
    webhook_url: str = Field(max_length=2048)
    hooks: dict[str, bool] | None = None
    timeout_seconds: int = Field(default=5, ge=1, le=30)
    enabled: bool = True


class GuardrailConfigResponse(BaseModel):
    id: int
    namespace: str
    user_id: str
    webhook_url: str
    enabled: bool
    hooks: dict[str, bool]
    timeout_seconds: int
    signing_secret: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# -- Endpoints --


@router.get("", response_model=GuardrailConfigResponse | None)
async def get_guardrail_config(
    session_context: SessionContext = Depends(get_session_context),
):
    """Get the current user's guardrail webhook configuration."""
    with db_session() as db:
        repo = LabsGuardrailConfigRepository(db, session_context)
        config = repo.get_for_current_user()
        if not config:
            return None
        result = config.to_dict()
        result["signing_secret"] = config.signing_secret
        return result


@router.put("", response_model=GuardrailConfigResponse, status_code=200)
async def upsert_guardrail_config(
    body: GuardrailConfigRequest,
    session_context: SessionContext = Depends(get_session_context),
):
    """Create or update the guardrail webhook configuration."""
    with db_session() as db:
        repo = LabsGuardrailConfigRepository(db, session_context)
        try:
            config, _created = repo.upsert(
                webhook_url=body.webhook_url,
                hooks=body.hooks,
                timeout_seconds=body.timeout_seconds,
                enabled=body.enabled,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        result = config.to_dict()
        result["signing_secret"] = config.signing_secret
        return result


@router.post("/toggle", response_model=GuardrailConfigResponse)
async def toggle_guardrail_enabled(
    session_context: SessionContext = Depends(get_session_context),
):
    """Toggle the enabled flag on the guardrail config."""
    with db_session() as db:
        repo = LabsGuardrailConfigRepository(db, session_context)
        config = repo.toggle_enabled()
        if not config:
            raise HTTPException(
                status_code=404, detail="No guardrail config found"
            )
        result = config.to_dict()
        result["signing_secret"] = config.signing_secret
        return result


@router.post("/rotate-secret", response_model=GuardrailConfigResponse)
async def rotate_signing_secret(
    session_context: SessionContext = Depends(get_session_context),
):
    """Rotate the HMAC signing secret."""
    with db_session() as db:
        repo = LabsGuardrailConfigRepository(db, session_context)
        config = repo.rotate_secret()
        if not config:
            raise HTTPException(
                status_code=404, detail="No guardrail config found"
            )
        result = config.to_dict()
        result["signing_secret"] = config.signing_secret
        return result


@router.delete("", status_code=204)
async def delete_guardrail_config(
    session_context: SessionContext = Depends(get_session_context),
):
    """Delete the guardrail webhook configuration."""
    with db_session() as db:
        repo = LabsGuardrailConfigRepository(db, session_context)
        deleted = repo.delete_config()
        if not deleted:
            raise HTTPException(
                status_code=404, detail="No guardrail config found"
            )


@router.post("/test")
async def test_webhook_delivery(
    session_context: SessionContext = Depends(get_session_context),
):
    """Send a test before_tool hook to the user's webhook and return the result."""
    svc = GuardrailHookService(
        session_context=session_context, workflow_id="wf_labs_test"
    )
    outcome = await svc.invoke(
        HookKind.before_tool,
        tool_name="test_tool",
        tool_source="native",
        tool_arguments={"example_param": "hello_from_labs"},
    )
    return {
        "outcome": outcome.value,
        "message": f"Hook fired with outcome: {outcome.value}",
    }


@router.get("/activity")
async def get_guardrail_activity(
    session_context: SessionContext = Depends(get_session_context),
    limit: int = 50,
):
    """Get recent guardrail events for the current user."""
    with db_session() as db:
        repo = CTFEventRepository(db, session_context)
        events = repo.get_events(limit=min(limit, 200), category="agent")

    return [
        ev.to_dict()
        for ev in events
        if ev.agent_name == "guardrail"
    ]
