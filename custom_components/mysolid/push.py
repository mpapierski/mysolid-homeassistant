from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import io
import json
import socket
import ssl
import uuid
from collections import deque
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import aiohttp

from ._proto.android_checkin_pb2 import AndroidCheckinProto, ChromeBuildProto
from ._proto.checkin_pb2 import AndroidCheckinRequest, AndroidCheckinResponse
from ._proto.mcs_pb2 import (
    Close,
    DataMessageStanza,
    HeartbeatAck,
    HeartbeatPing,
    IqStanza,
    LoginRequest,
    LoginResponse,
    SelectiveAck,
)
from .constants import (
    APP_VERSION_CODE,
    APP_VERSION_NAME,
    FIREBASE_API_KEY,
    FIREBASE_APP_ID,
    FIREBASE_PROJECT_ID,
    FIREBASE_SENDER_ID,
    PACKAGE_NAME,
)
from .crypto import decrypt_push_message

if TYPE_CHECKING:
    from .client import MySolidClient


GOOGLE_API_KEY = FIREBASE_API_KEY
GOOGLE_APP_ID = FIREBASE_APP_ID
GOOGLE_PROJECT_ID = FIREBASE_PROJECT_ID
GOOGLE_SENDER_ID = FIREBASE_SENDER_ID
ANDROID_PACKAGE_NAME = PACKAGE_NAME
CLIENT_LIBRARY_VERSION = "fiid-21.0.0"
GMS_VERSION_CODE = "250024000"
ANDROID_SDK_LEVEL = "34"
CHECKIN_DEVICE_TYPE = 3
CHECKIN_CHROME_PLATFORM = 6
CHECKIN_CHROME_CHANNEL = 1

CHECKIN_URL = "https://android.clients.google.com/checkin"
REGISTER_URL = "https://android.clients.google.com/c2dm/register3"
FIS_BASE_URL = "https://firebaseinstallations.googleapis.com/v1"
MCS_HOST = "mtalk.google.com"
MCS_PORT = 5228
MCS_VERSION = 41
MCS_CLIENT_ID = "chrome-63.0.3234.0"

PACKET_BY_TAG: list[type[Any] | str] = [
    HeartbeatPing,
    HeartbeatAck,
    LoginRequest,
    LoginResponse,
    Close,
    "MessageStanza",
    "PresenceStanza",
    IqStanza,
    DataMessageStanza,
    "BatchPresenceStanza",
    "StreamErrorStanza",
    "HttpRequest",
    "HttpResponse",
    "BindAccountRequest",
    "BindAccountResponse",
    "TalkMetadata",
    "NumProtoTypes",
    "StreamAck",
    SelectiveAck,
]


class PushError(RuntimeError):
    """Base error for experimental push support."""


class PushRegistrationError(PushError):
    """Push token bootstrap failed."""


class PushProtocolError(PushError):
    """Unexpected response while talking to the MCS socket."""


@dataclass(slots=True)
class FirebaseInstallation:
    fid: str
    refresh_token: str
    auth_token: str
    auth_expires_in: str

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> FirebaseInstallation:
        return cls(
            fid=payload["fid"],
            refresh_token=payload["refreshToken"],
            auth_token=payload["authToken"]["token"],
            auth_expires_in=payload["authToken"]["expiresIn"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fid": self.fid,
            "refresh_token": self.refresh_token,
            "auth_token": self.auth_token,
            "auth_expires_in": self.auth_expires_in,
        }


@dataclass(slots=True)
class PushCredentials:
    android_id: int
    security_token: int
    registration_token: str
    installation: FirebaseInstallation
    sender_id: str = GOOGLE_SENDER_ID
    package_name: str = ANDROID_PACKAGE_NAME
    app_id: str = GOOGLE_APP_ID
    api_key: str = GOOGLE_API_KEY
    project_id: str = GOOGLE_PROJECT_ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "android_id": self.android_id,
            "security_token": self.security_token,
            "registration_token": self.registration_token,
            "installation": self.installation.to_dict(),
            "sender_id": self.sender_id,
            "package_name": self.package_name,
            "app_id": self.app_id,
            "api_key": self.api_key,
            "project_id": self.project_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PushCredentials:
        return cls(
            android_id=int(payload["android_id"]),
            security_token=int(payload["security_token"]),
            registration_token=payload["registration_token"],
            installation=FirebaseInstallation(
                fid=payload["installation"]["fid"],
                refresh_token=payload["installation"]["refresh_token"],
                auth_token=payload["installation"]["auth_token"],
                auth_expires_in=payload["installation"]["auth_expires_in"],
            ),
            sender_id=payload.get("sender_id", GOOGLE_SENDER_ID),
            package_name=payload.get("package_name", ANDROID_PACKAGE_NAME),
            app_id=payload.get("app_id", GOOGLE_APP_ID),
            api_key=payload.get("api_key", GOOGLE_API_KEY),
            project_id=payload.get("project_id", GOOGLE_PROJECT_ID),
        )


@dataclass(slots=True)
class MySolidPushMessage:
    persistent_id: str
    category: str
    sender: str
    recipient: str
    app_data: dict[str, str]
    raw_data: bytes | None = None
    decrypted_bytes: bytes | None = None
    decrypted_json: dict[str, Any] | None = None

    @property
    def title(self) -> str | None:
        return self.app_data.get("title")

    @property
    def body(self) -> str | None:
        return self.app_data.get("body")

    @property
    def click_action(self) -> str | None:
        return self.app_data.get("click_action")

    @property
    def encrypted_message(self) -> str | None:
        return self.app_data.get("message")

    @property
    def event_bundle_id(self) -> str | None:
        return self.app_data.get("eventBundleId")


def _gzip_json(data: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
        gz.write(json.dumps(data).encode("utf-8"))
    return buffer.getvalue()


def _generate_fid() -> str:
    raw = bytearray(uuid.uuid4().bytes + b"\x00")
    raw[16] = raw[0]
    raw[0] = (raw[0] & 0x0F) | 0x70
    return base64.urlsafe_b64encode(bytes(raw)).decode("ascii").rstrip("=")[:22]


def _firebase_app_name_hash() -> str:
    digest = hashlib.sha1(b"[DEFAULT]").digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _encode_varint32(value: int) -> bytes:
    encoded = bytearray()
    while value:
        current = value & 0x7F
        value >>= 7
        if value:
            current |= 0x80
        encoded.append(current)
    return bytes(encoded or b"\x00")


async def _read_varint32(reader: asyncio.StreamReader) -> int:
    value = 0
    shift = 0
    while True:
        current = (await reader.readexactly(1))[0]
        value |= (current & 0x7F) << shift
        if current & 0x80 == 0:
            return value
        shift += 7


async def _send_packet(writer: asyncio.StreamWriter, packet: Any) -> None:
    tag = PACKET_BY_TAG.index(type(packet))
    payload = packet.SerializeToString()
    writer.write(bytes([MCS_VERSION, tag]) + _encode_varint32(len(payload)) + payload)
    await writer.drain()


async def _recv_packet(
    reader: asyncio.StreamReader,
    *,
    first: bool,
) -> tuple[int, Any]:
    if first:
        version, tag = await reader.readexactly(2)
        if version not in (38, MCS_VERSION):
            raise PushProtocolError(f"Unsupported MCS version {version}")
    else:
        tag = (await reader.readexactly(1))[0]
    size = await _read_varint32(reader)
    payload = await reader.readexactly(size)
    packet_type = PACKET_BY_TAG[tag]
    if isinstance(packet_type, str):
        return tag, payload
    message = packet_type()
    message.ParseFromString(payload)
    return tag, message


def _app_data_map(stanza: DataMessageStanza) -> dict[str, str]:
    return {entry.key: entry.value for entry in stanza.app_data}


def _parse_register_response(text: str) -> str:
    if text.startswith("token="):
        return text.split("=", 1)[1]
    if text.startswith("Error="):
        raise PushRegistrationError(text.split("=", 1)[1])
    raise PushRegistrationError(f"Unexpected register3 response: {text}")


def _build_checkin_request(
    *,
    android_id: int | None = None,
    security_token: int | None = None,
) -> AndroidCheckinRequest:
    chrome = ChromeBuildProto()
    # Google accepts register3 for this package only when the check-in
    # identifies an Android Chrome build, not a Linux one.
    chrome.platform = CHECKIN_CHROME_PLATFORM
    chrome.chrome_version = MCS_CLIENT_ID.removeprefix("chrome-")
    chrome.channel = CHECKIN_CHROME_CHANNEL

    checkin = AndroidCheckinProto()
    checkin.type = CHECKIN_DEVICE_TYPE
    checkin.chrome_build.CopyFrom(chrome)

    payload = AndroidCheckinRequest()
    payload.user_serial_number = 0
    payload.checkin.CopyFrom(checkin)
    payload.version = 3
    if android_id is not None:
        payload.id = android_id
    if security_token is not None:
        payload.security_token = security_token
    return payload


async def _check_in(
    session: aiohttp.ClientSession,
    *,
    android_id: int | None = None,
    security_token: int | None = None,
) -> tuple[int, int]:
    payload = _build_checkin_request(
        android_id=android_id,
        security_token=security_token,
    )

    async with session.post(
        CHECKIN_URL,
        data=payload.SerializeToString(),
        headers={"Content-Type": "application/x-protobuf"},
    ) as response:
        response.raise_for_status()
        message = AndroidCheckinResponse()
        message.ParseFromString(await response.read())
        return int(message.android_id), int(message.security_token)


async def _create_installation(
    session: aiohttp.ClientSession,
    *,
    api_key: str,
    app_id: str,
    project_id: str,
    package_name: str,
) -> FirebaseInstallation:
    async with session.post(
        f"{FIS_BASE_URL}/projects/{project_id}/installations",
        data=_gzip_json(
            {
                "fid": _generate_fid(),
                "appId": app_id,
                "authVersion": "FIS_v2",
                "sdkVersion": "a:16.3.4",
            }
        ),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Content-Encoding": "gzip",
            "Cache-Control": "no-cache",
            "X-Android-Package": package_name,
            "x-goog-api-key": api_key,
        },
    ) as response:
        response.raise_for_status()
        data = await response.json()
        return FirebaseInstallation.from_json(data)


async def refresh_installation_auth(
    session: aiohttp.ClientSession,
    credentials: PushCredentials,
) -> str:
    async with session.post(
        f"{FIS_BASE_URL}/projects/{credentials.project_id}/installations/"
        f"{credentials.installation.fid}/authTokens:generate",
        data=_gzip_json({"installation": {"sdkVersion": "a:16.3.4"}}),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Content-Encoding": "gzip",
            "Cache-Control": "no-cache",
            "X-Android-Package": credentials.package_name,
            "x-goog-api-key": credentials.api_key,
            "Authorization": f"FIS_v2 {credentials.installation.refresh_token}",
        },
    ) as response:
        response.raise_for_status()
        data = await response.json()
        credentials.installation.auth_token = data["token"]
        credentials.installation.auth_expires_in = data["expiresIn"]
        return credentials.installation.auth_token


async def _register_fcm_token(
    session: aiohttp.ClientSession,
    *,
    android_id: int,
    security_token: int,
    installation: FirebaseInstallation,
    sender_id: str,
    package_name: str,
    app_id: str,
) -> str:
    payload = {
        "scope": "FCM",
        "sender": sender_id,
        "subtype": sender_id,
        "appid": installation.fid,
        "gmp_app_id": app_id,
        "gmsv": GMS_VERSION_CODE,
        "osv": ANDROID_SDK_LEVEL,
        "app_ver": APP_VERSION_CODE,
        "app_ver_name": APP_VERSION_NAME,
        "firebase-app-name-hash": _firebase_app_name_hash(),
        "cliv": CLIENT_LIBRARY_VERSION,
        "X-subtype": sender_id,
        "app": package_name,
        "device": str(android_id),
    }
    async with session.post(
        REGISTER_URL,
        data=payload,
        headers={
            "Authorization": f"AidLogin {android_id}:{security_token}",
            "x-goog-firebase-installations-auth": installation.auth_token,
        },
    ) as response:
        response.raise_for_status()
        return _parse_register_response(await response.text())


async def bootstrap_push_credentials(
    session: aiohttp.ClientSession | None = None,
    *,
    sender_id: str = GOOGLE_SENDER_ID,
    package_name: str = ANDROID_PACKAGE_NAME,
    app_id: str = GOOGLE_APP_ID,
    api_key: str = GOOGLE_API_KEY,
    project_id: str = GOOGLE_PROJECT_ID,
    register_attempts: int = 8,
    retry_delay_seconds: float = 0.75,
) -> PushCredentials:
    """Bootstrap Google device/MCS state and return a usable FCM token."""
    owns_session = session is None
    if owns_session:
        timeout = aiohttp.ClientTimeout(total=30)
        session = aiohttp.ClientSession(timeout=timeout)
    assert session is not None
    try:
        last_error: PushRegistrationError | None = None
        for attempt in range(1, register_attempts + 1):
            installation = await _create_installation(
                session,
                api_key=api_key,
                app_id=app_id,
                project_id=project_id,
                package_name=package_name,
            )
            android_id, security_token = await _check_in(session)
            try:
                registration_token = await _register_fcm_token(
                    session,
                    android_id=android_id,
                    security_token=security_token,
                    installation=installation,
                    sender_id=sender_id,
                    package_name=package_name,
                    app_id=app_id,
                )
            except PushRegistrationError as exc:
                last_error = exc
                if attempt >= register_attempts:
                    raise
                if retry_delay_seconds > 0:
                    await asyncio.sleep(retry_delay_seconds * attempt)
                continue

            await _check_in(
                session,
                android_id=android_id,
                security_token=security_token,
            )
            return PushCredentials(
                android_id=android_id,
                security_token=security_token,
                registration_token=registration_token,
                installation=installation,
                sender_id=sender_id,
                package_name=package_name,
                app_id=app_id,
                api_key=api_key,
                project_id=project_id,
            )
        if last_error is not None:
            raise last_error
        raise PushRegistrationError("Push bootstrap failed without a registration response")
    finally:
        if owns_session:
            await session.close()


class MySolidPushListener:
    """Experimental async listener for MySolid FCM pushes over the MCS socket."""

    def __init__(
        self,
        credentials: PushCredentials,
        *,
        access_token: str,
        package_name: str | None = None,
        persistent_ids: Iterable[str] = (),
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._credentials = credentials
        self._access_token = access_token
        self._package_name = package_name or credentials.package_name
        self._persistent_ids: deque[str] = deque(persistent_ids, maxlen=256)
        self._persistent_set = set(self._persistent_ids)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._ssl_context = ssl_context or ssl.create_default_context()

    @property
    def persistent_ids(self) -> list[str]:
        return list(self._persistent_ids)

    def __aiter__(self) -> AsyncIterator[MySolidPushMessage]:
        return self.iter_messages()

    async def __aenter__(self) -> MySolidPushListener:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def connect(self) -> None:
        if self._reader is not None and self._writer is not None:
            return
        reader, writer = await asyncio.open_connection(
            MCS_HOST,
            MCS_PORT,
            ssl=self._ssl_context,
            family=socket.AF_INET,
        )
        self._reader = reader
        self._writer = writer

        login = LoginRequest()
        login.adaptive_heartbeat = False
        login.auth_service = LoginRequest.ANDROID_ID
        login.auth_token = str(self._credentials.security_token)
        login.id = MCS_CLIENT_ID
        login.domain = "mcs.android.com"
        login.device_id = f"android-{self._credentials.android_id:x}"
        login.network_type = 1
        login.resource = str(self._credentials.android_id)
        login.user = str(self._credentials.android_id)
        login.use_rmq2 = True
        login.setting.add(name="new_vc", value="1")
        login.received_persistent_id.extend(self.persistent_ids)

        await _send_packet(writer, login)
        tag, packet = await _recv_packet(reader, first=True)
        if tag != PACKET_BY_TAG.index(LoginResponse) or not isinstance(packet, LoginResponse):
            raise PushProtocolError(f"Expected LoginResponse, got tag {tag}")

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionError, TimeoutError):
                pass
        self._reader = None
        self._writer = None

    async def register_with_server(self, client: MySolidClient) -> None:
        await client.update_firebase_token(
            self._credentials.registration_token,
            device_id=client.device_id,
        )

    async def iter_messages(self) -> AsyncIterator[MySolidPushMessage]:
        while True:
            message = await self.next_message()
            if message is not None:
                yield message

    async def next_message(self) -> MySolidPushMessage | None:
        if self._reader is None or self._writer is None:
            await self.connect()
        assert self._reader is not None
        assert self._writer is not None

        tag, packet = await _recv_packet(self._reader, first=False)
        if tag == PACKET_BY_TAG.index(HeartbeatPing) and isinstance(packet, HeartbeatPing):
            await _send_packet(self._writer, HeartbeatAck())
            return None
        if tag == PACKET_BY_TAG.index(Close):
            raise PushProtocolError("MCS connection closed by remote peer")
        if tag != PACKET_BY_TAG.index(DataMessageStanza) or not isinstance(packet, DataMessageStanza):
            return None

        if packet.immediate_ack:
            ack = SelectiveAck()
            ack.id.append(packet.persistent_id)
            await _send_packet(self._writer, ack)

        if packet.category != self._package_name:
            return None
        if packet.persistent_id in self._persistent_set:
            return None

        self._persistent_ids.append(packet.persistent_id)
        self._persistent_set.add(packet.persistent_id)
        while len(self._persistent_set) > self._persistent_ids.maxlen:
            oldest = self._persistent_ids.popleft()
            self._persistent_set.discard(oldest)

        app_data = _app_data_map(packet)
        decrypted_bytes: bytes | None = None
        decrypted_json: dict[str, Any] | None = None
        encrypted_message = app_data.get("message")
        if encrypted_message:
            decrypted_bytes = decrypt_push_message(encrypted_message, self._access_token)
            try:
                decrypted_json = json.loads(decrypted_bytes.decode("utf-8"))
            except json.JSONDecodeError:
                decrypted_json = None

        return MySolidPushMessage(
            persistent_id=packet.persistent_id,
            category=packet.category,
            sender=getattr(packet, "from"),
            recipient=packet.to,
            app_data=app_data,
            raw_data=packet.raw_data if packet.HasField("raw_data") else None,
            decrypted_bytes=decrypted_bytes,
            decrypted_json=decrypted_json,
        )

    async def listen_forever(self) -> MySolidPushMessage:
        while True:
            message = await self.next_message()
            if message is not None:
                return message
