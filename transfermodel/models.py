import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from transfermodel import config


class UpstreamProvider(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    api_type: Literal["anthropic", "openai"] = "anthropic"
    base_url: str = ""
    api_key: str = ""
    models: list[str] = Field(default_factory=list)
    default_model: str | None = None
    priority: int = Field(default=config.DEFAULT_PROVIDER_PRIORITY)
    enabled: bool = Field(default=config.DEFAULT_PROVIDER_ENABLED)
    timeout_seconds: int = Field(default=config.DEFAULT_PROVIDER_TIMEOUT)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ServerSettings(BaseModel):
    listen_host: str = Field(default=config.DEFAULT_HOST)
    listen_port: int = Field(default=config.DEFAULT_PORT)
    log_level: str = Field(default=config.DEFAULT_LOG_LEVEL)


def mask_api_key(key: str) -> str:
    if len(key) <= 12:
        return "****"
    return key[:8] + "*" * (len(key) - 12) + key[-4:]


class ProviderResponse(BaseModel):
    id: str
    name: str
    api_type: str
    base_url: str
    api_key_masked: str
    models: list[str]
    default_model: str | None
    priority: int
    enabled: bool
    timeout_seconds: int
    created_at: str
    updated_at: str

    @classmethod
    def from_provider(cls, p: UpstreamProvider) -> "ProviderResponse":
        return cls(
            id=p.id,
            name=p.name,
            api_type=p.api_type,
            base_url=p.base_url,
            api_key_masked=mask_api_key(p.api_key),
            models=p.models,
            default_model=p.default_model,
            priority=p.priority,
            enabled=p.enabled,
            timeout_seconds=p.timeout_seconds,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
