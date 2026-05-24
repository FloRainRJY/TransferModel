import json
from pathlib import Path

from transfermodel import config
from transfermodel.models import UpstreamProvider, ServerSettings


def _data_dir() -> Path:
    return config.DEFAULT_DATA_DIR


def _ensure_data_dir() -> Path:
    d = _data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _providers_path() -> Path:
    return _ensure_data_dir() / "providers.json"


def _settings_path() -> Path:
    return _ensure_data_dir() / "settings.json"


def load_providers() -> list[UpstreamProvider]:
    path = _providers_path()
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [UpstreamProvider(**item) for item in data]


def save_providers(providers: list[UpstreamProvider]) -> None:
    path = _providers_path()
    data = [p.model_dump() for p in providers]
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_settings() -> ServerSettings:
    path = _settings_path()
    if not path.exists():
        return ServerSettings()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ServerSettings(**data)


def save_settings(settings: ServerSettings) -> None:
    path = _settings_path()
    data = settings.model_dump()
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
