from __future__ import annotations

from custom_components.mysolid.push import (
    CHECKIN_CHROME_CHANNEL,
    CHECKIN_CHROME_PLATFORM,
    CHECKIN_DEVICE_TYPE,
    _build_checkin_request,
)


def test_build_checkin_request_uses_android_chrome_identity() -> None:
    request = _build_checkin_request()

    assert request.version == 3
    assert request.user_serial_number == 0
    assert request.checkin.type == CHECKIN_DEVICE_TYPE
    assert request.checkin.chrome_build.platform == CHECKIN_CHROME_PLATFORM
    assert request.checkin.chrome_build.channel == CHECKIN_CHROME_CHANNEL
    assert request.checkin.chrome_build.chrome_version == "63.0.3234.0"


def test_build_checkin_request_can_include_existing_device_credentials() -> None:
    request = _build_checkin_request(
        android_id=123,
        security_token=456,
    )

    assert request.id == 123
    assert request.security_token == 456
