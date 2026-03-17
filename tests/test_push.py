from __future__ import annotations

import pytest

from custom_components.mysolid.push import (
    FirebaseInstallation,
    MySolidPushListener,
    PushCredentials,
    PushRegistrationError,
    bootstrap_push_credentials,
)


class RecordingClient:
    def __init__(self) -> None:
        self.device_id = "ANDROID_ID#deadbeefdeadbeef"
        self.calls: list[tuple[str, str | None]] = []

    async def update_firebase_token(
        self,
        new_firebase_token: str,
        *,
        device_id: str | None = None,
    ) -> None:
        self.calls.append((new_firebase_token, device_id))


class TimeoutWriter:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        raise TimeoutError("ssl shutdown timed out")


@pytest.mark.asyncio
async def test_register_with_server_uses_client_device_and_fcm_token() -> None:
    credentials = PushCredentials(
        android_id=123,
        security_token=456,
        registration_token="fcm-token-123",
        installation=FirebaseInstallation(
            fid="abcdefghijklmnopqrstuv"[:22],
            refresh_token="refresh-token",
            auth_token="auth-token",
            auth_expires_in="604800s",
        ),
    )
    listener = MySolidPushListener(
        credentials,
        access_token="12345678-1234-1234-1234-123456789abc",
    )
    client = RecordingClient()

    await listener.register_with_server(client)

    assert client.calls == [("fcm-token-123", "ANDROID_ID#deadbeefdeadbeef")]


@pytest.mark.asyncio
async def test_bootstrap_push_credentials_retries_registration_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    installation = FirebaseInstallation(
        fid="abcdefghijklmnopqrstuv"[:22],
        refresh_token="refresh-token",
        auth_token="auth-token",
        auth_expires_in="604800s",
    )
    register_calls = 0
    checkin_calls: list[tuple[int | None, int | None]] = []

    async def fake_create_installation(*args: object, **kwargs: object) -> FirebaseInstallation:
        return installation

    async def fake_check_in(
        *args: object,
        android_id: int | None = None,
        security_token: int | None = None,
        **kwargs: object,
    ) -> tuple[int, int]:
        checkin_calls.append((android_id, security_token))
        return (111, 222)

    async def fake_register_fcm_token(*args: object, **kwargs: object) -> str:
        nonlocal register_calls
        register_calls += 1
        if register_calls < 3:
            raise PushRegistrationError("PHONE_REGISTRATION_ERROR")
        return "fcm-token-123"

    monkeypatch.setattr(
        "custom_components.mysolid.push._create_installation",
        fake_create_installation,
    )
    monkeypatch.setattr("custom_components.mysolid.push._check_in", fake_check_in)
    monkeypatch.setattr(
        "custom_components.mysolid.push._register_fcm_token",
        fake_register_fcm_token,
    )

    class DummySession:
        pass

    credentials = await bootstrap_push_credentials(
        session=DummySession(),  # type: ignore[arg-type]
        register_attempts=3,
        retry_delay_seconds=0,
    )

    assert credentials.registration_token == "fcm-token-123"
    assert register_calls == 3
    assert checkin_calls == [(None, None), (None, None), (None, None), (111, 222)]


@pytest.mark.asyncio
async def test_listener_close_ignores_ssl_shutdown_timeout() -> None:
    credentials = PushCredentials(
        android_id=123,
        security_token=456,
        registration_token="fcm-token-123",
        installation=FirebaseInstallation(
            fid="abcdefghijklmnopqrstuv"[:22],
            refresh_token="refresh-token",
            auth_token="auth-token",
            auth_expires_in="604800s",
        ),
    )
    listener = MySolidPushListener(
        credentials,
        access_token="12345678-1234-1234-1234-123456789abc",
    )
    writer = TimeoutWriter()
    listener._writer = writer  # type: ignore[assignment]
    listener._reader = object()  # type: ignore[assignment]

    await listener.close()

    assert writer.closed is True
    assert listener._writer is None
    assert listener._reader is None
