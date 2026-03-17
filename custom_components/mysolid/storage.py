from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .models import Session
from .push import PushCredentials

STORAGE_VERSION = 1


@dataclass(slots=True)
class StoredState:
    session: Session
    push_credentials: PushCredentials | None = None
    persistent_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StoredState:
        raw_session = payload.get("session")
        if not isinstance(raw_session, dict):
            raise ValueError("Missing session payload")

        raw_push_credentials = payload.get("push_credentials")
        push_credentials = None
        if isinstance(raw_push_credentials, dict):
            push_credentials = PushCredentials.from_dict(raw_push_credentials)

        raw_persistent_ids = payload.get("persistent_ids")
        persistent_ids: tuple[str, ...] = ()
        if isinstance(raw_persistent_ids, list):
            persistent_ids = tuple(str(item) for item in raw_persistent_ids)

        return cls(
            session=Session.from_dict(raw_session),
            push_credentials=push_credentials,
            persistent_ids=persistent_ids,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STORAGE_VERSION,
            "session": self.session.to_dict(),
            "push_credentials": (
                self.push_credentials.to_dict() if self.push_credentials else None
            ),
            "persistent_ids": list(self.persistent_ids),
        }


class MySolidStateStore:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}",
        )

    async def async_load(self) -> StoredState | None:
        if (payload := await self._store.async_load()) is None:
            return None
        return StoredState.from_dict(payload)

    async def async_save(self, state: StoredState) -> None:
        await self._store.async_save(state.to_dict())

    async def async_remove(self) -> None:
        await self._store.async_remove()
