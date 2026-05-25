"""Local credential binding store for Discord academy operations."""

from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from miho_constants import get_miho_home
from utils import atomic_json_write


@dataclass(frozen=True)
class AcademyBinding:
    discord_user_id: str
    user_id: str
    email: str
    name: str
    role: str
    academy_id: str
    academy_name: str
    token_ciphertext: str
    created_at: int
    updated_at: int


def store_dir() -> Path:
    return get_miho_home() / "academy_ops"


def key_path() -> Path:
    return store_dir() / "secret.key"


def bindings_path() -> Path:
    return store_dir() / "bindings.json"


def load_bindings() -> dict[str, AcademyBinding]:
    path = bindings_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    bindings: dict[str, AcademyBinding] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            bindings[str(key)] = AcademyBinding(**value)
        except TypeError:
            continue
    return bindings


def save_binding(binding: AcademyBinding) -> None:
    bindings = load_bindings()
    bindings[binding.discord_user_id] = binding
    payload = {key: asdict(value) for key, value in bindings.items()}
    _secure_parent(bindings_path())
    atomic_json_write(bindings_path(), payload)
    _chmod_owner_only(bindings_path())


def get_binding(discord_user_id: str) -> AcademyBinding | None:
    return load_bindings().get(str(discord_user_id))


def delete_binding(discord_user_id: str) -> bool:
    bindings = load_bindings()
    existed = str(discord_user_id) in bindings
    bindings.pop(str(discord_user_id), None)
    payload = {key: asdict(value) for key, value in bindings.items()}
    _secure_parent(bindings_path())
    atomic_json_write(bindings_path(), payload)
    _chmod_owner_only(bindings_path())
    return existed


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str) -> str | None:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, OSError, ValueError):
        return None


def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def _load_or_create_key() -> bytes:
    path = key_path()
    _secure_parent(path)
    if path.exists():
        raw = path.read_bytes().strip()
        base64.urlsafe_b64decode(raw)
        return raw
    key = Fernet.generate_key()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(key)
        handle.flush()
        os.fsync(handle.fileno())
    _chmod_owner_only(path)
    return key


def _secure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass


def _chmod_owner_only(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def binding_public_payload(binding: AcademyBinding) -> dict[str, Any]:
    payload = asdict(binding)
    payload.pop("token_ciphertext", None)
    return payload
