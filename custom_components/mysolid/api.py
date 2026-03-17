from __future__ import annotations

import json
import platform
import socket
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin

import aiohttp

from .constants import (
    APP_VERSION_CODE,
    APP_VERSION_NAME,
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_DEVICE_NAME,
    DEFAULT_HOST,
    DEFAULT_READ_TIMEOUT_SECONDS,
    DEVICE_ID_PREFIX,
)
from .exceptions import (
    AuthErrorDetails,
    MySolidApiError,
    MySolidAuthError,
    MySolidSessionError,
)
from .models import AccessToken, PropertyDetails, PropertyDetailsResponse, Session

JSON = dict[str, Any] | list[Any] | str | int | float | bool | None


def generate_device_id() -> str:
    return f"{DEVICE_ID_PREFIX}{uuid.uuid4().hex[:16]}"


def default_device_name() -> str:
    hostname = socket.gethostname().strip()
    return hostname or DEFAULT_DEVICE_NAME


class MySolidClient:
    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        email: str | None = None,
        access_token: str | AccessToken | None = None,
        device_id: str | None = None,
        device_name: str | None = None,
        firebase_token: str | None = None,
        session: aiohttp.ClientSession | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
    ) -> None:
        self._host = host if host.endswith("/") else f"{host}/"
        self._email = email
        self._device_id = device_id or generate_device_id()
        self._device_name = device_name or default_device_name()
        self._firebase_token = firebase_token
        self._access_token = (
            access_token
            if isinstance(access_token, AccessToken) or access_token is None
            else AccessToken(value=access_token)
        )
        self._timeout = timeout or aiohttp.ClientTimeout(
            connect=DEFAULT_CONNECT_TIMEOUT_SECONDS,
            sock_read=DEFAULT_READ_TIMEOUT_SECONDS,
        )
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> MySolidClient:
        await self._ensure_session()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    @property
    def session(self) -> Session:
        return Session(
            host=self._host,
            email=self._email,
            device_id=self._device_id,
            device_name=self._device_name,
            access_token=self._access_token,
            firebase_token=self._firebase_token,
        )

    @property
    def host(self) -> str:
        return self._host

    @property
    def email(self) -> str | None:
        return self._email

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def access_token(self) -> AccessToken | None:
        return self._access_token

    @property
    def firebase_token(self) -> str | None:
        return self._firebase_token

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None and bool(self._access_token.value)

    def configure_session(
        self,
        *,
        email: str | None = None,
        access_token: str | AccessToken | None = None,
        device_id: str | None = None,
        device_name: str | None = None,
        firebase_token: str | None = None,
    ) -> None:
        if email is not None:
            self._email = email
        if access_token is not None:
            self._access_token = (
                access_token
                if isinstance(access_token, AccessToken)
                else AccessToken(value=access_token)
            )
        if device_id is not None:
            self._device_id = device_id
        if device_name is not None:
            self._device_name = device_name
        if firebase_token is not None:
            self._firebase_token = firebase_token

    async def close(self) -> None:
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()

    async def login(
        self,
        email: str,
        password: str,
        *,
        device_id: str | None = None,
        device_name: str | None = None,
        firebase_token: str | None = None,
    ) -> Session:
        if device_id is not None:
            self._device_id = device_id
        if device_name is not None:
            self._device_name = device_name
        if firebase_token is not None:
            self._firebase_token = firebase_token
        payload = {
            "email": email,
            "password": password,
            "deviceId": self._device_id,
            "deviceName": self._device_name,
        }
        if self._firebase_token is not None:
            payload["firebaseToken"] = self._firebase_token
        response = await self._request_json(
            "POST",
            "api/authorization",
            json_body=payload,
            authenticated=False,
        )
        if not isinstance(response, Mapping):
            raise MySolidApiError(500, "Unexpected login response", payload=response)
        self._email = email
        self._access_token = AccessToken.from_api(response)
        return self.session

    async def change_password(
        self,
        *,
        email: str,
        old_password: str,
        new_password: str,
    ) -> None:
        await self._request_empty(
            "PUT",
            "changeUserPassword",
            json_body={
                "email": email,
                "oldPasswd": old_password,
                "newPasswd": new_password,
            },
            authenticated=False,
        )

    async def register_account(self, payload: Mapping[str, Any]) -> None:
        await self._request_empty(
            "POST",
            "mobile/register",
            json_body=dict(payload),
            authenticated=False,
        )

    async def reset_password(self, email_address: str, *, flag_android: bool = True) -> None:
        await self._request_empty(
            "POST",
            "mobile/resetPassword",
            json_body={
                "emailAddress": email_address,
                "flagAndroid": flag_android,
            },
            authenticated=False,
        )

    async def delete_user(self) -> None:
        await self._request_empty("DELETE", "api/deleteUser")

    async def logout_push_token(self, *, device_id: str | None = None) -> None:
        await self._request_empty(
            "DELETE",
            "api/firebase/delete",
            json_body={"deviceId": device_id or self._device_id},
        )

    async def update_firebase_token(
        self,
        new_firebase_token: str,
        *,
        device_id: str | None = None,
    ) -> None:
        self._firebase_token = new_firebase_token
        await self._request_empty(
            "PUT",
            "api/firebase/token",
            json_body={
                "deviceId": device_id or self._device_id,
                "newFirebaseToken": new_firebase_token,
            },
        )

    async def get_property_details(self) -> PropertyDetailsResponse:
        response = await self._request_json("GET", "api/v1.3/property-details")
        if not isinstance(response, Mapping):
            raise MySolidApiError(500, "Unexpected property details response", payload=response)
        return PropertyDetailsResponse.from_api(response)

    async def get_property_summaries(self) -> tuple[PropertyDetails, ...]:
        return (await self.get_property_details()).properties

    async def get_permissions(self) -> set[str]:
        response = await self._request_json("GET", "api/permissions")
        if isinstance(response, list):
            return {str(item) for item in response}
        if isinstance(response, set):
            return {str(item) for item in response}
        raise MySolidApiError(500, "Unexpected permissions response", payload=response)

    async def get_relays(self, account_id: int) -> list[dict[str, Any]]:
        response = await self._request_json(
            "GET",
            "api/v1.3/transmitters/relaysWithPin",
            params={"accountId": account_id},
        )
        return self._expect_list_of_dicts(response, "relay list")

    async def update_relay_state(self, payload: Mapping[str, Any]) -> None:
        await self._request_empty(
            "PUT",
            "api/v1.3/transmitters/relays/updateState",
            json_body=dict(payload),
        )

    async def update_relay(self, payload: Mapping[str, Any]) -> None:
        await self._request_empty(
            "PUT",
            "api/v1.3/transmitters/relays/update",
            json_body=dict(payload),
        )

    async def list_alarms(self) -> list[dict[str, Any]]:
        response = await self._request_json("GET", "api/v1.4/alarms")
        return self._expect_list_of_dicts(response, "alarm list")

    async def report_alarm(
        self,
        *,
        property_id: int,
        location: Mapping[str, float] | None = None,
        alarm_type: str = "ALARM",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"propertyId": property_id, "type": alarm_type}
        if location is not None:
            payload["location"] = dict(location)
        response = await self._request_json("POST", "api/alarms", json_body=payload)
        return self._expect_dict(response, "alarm report response")

    async def cancel_alarm(self, event_id: int, *, pin: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"eventId": event_id}
        if pin is not None:
            payload["pin"] = pin
        response = await self._request_json("DELETE", "api/alarms", json_body=payload)
        return self._expect_dict(response, "alarm cancel response")

    async def confirm_alarm_received(self, event_bundle_id: int) -> None:
        await self._request_empty(
            "PUT",
            "api/alarms/confirm",
            json_body={"eventBundleId": event_bundle_id},
        )

    async def report_amber(
        self,
        *,
        property_id: int,
        duration_milliseconds: int,
        location: Mapping[str, float] | None = None,
        alarm_type: str = "ALARM",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "propertyId": property_id,
            "durationMilliseconds": duration_milliseconds,
            "type": alarm_type,
        }
        if location is not None:
            payload["location"] = dict(location)
        response = await self._request_json("POST", "api/ambers", json_body=payload)
        return self._expect_dict(response, "amber response")

    async def cancel_amber(self, amber_id: str, *, pin: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"amberId": amber_id}
        if pin is not None:
            payload["pin"] = pin
        response = await self._request_json("DELETE", "api/ambers", json_body=payload)
        return self._expect_dict(response, "amber cancel response")

    async def historical_event_list(
        self,
        property_id: int,
        *,
        page: int = 0,
        size: int = 20,
    ) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            f"api/historical-events/{property_id}",
            params={"page": page, "size": size},
        )
        return self._expect_dict(response, "historical event response")

    async def get_authorized_users(self, account_id: int) -> list[dict[str, Any]]:
        response = await self._request_json(
            "GET",
            "api/authorizedUsers",
            params={"accountId": account_id},
        )
        return self._expect_list_of_dicts(response, "authorized users")

    async def get_authorized_user_roles_and_phone_types(
        self,
        account_id: int,
    ) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "api/authorizedUsers/phoneTypesAndSinglePropertyRoles",
            params={"accountId": account_id},
        )
        return self._expect_dict(response, "authorized user metadata")

    async def register_authorized_user(self, payload: Mapping[str, Any]) -> None:
        await self._request_empty(
            "POST",
            "api/authorizedUsers",
            json_body=dict(payload),
        )

    async def edit_authorized_user(self, payload: Mapping[str, Any]) -> None:
        await self._request_empty(
            "PUT",
            "api/authorizedUsers",
            json_body=dict(payload),
        )

    async def delete_authorized_user(self, authorized_user_id: int) -> None:
        await self._request_empty("DELETE", f"api/authorizedUsers/{authorized_user_id}")

    async def reset_password_for_authorized_user(
        self,
        authorized_user_id: int,
        *,
        pin: str,
    ) -> None:
        await self._request_empty(
            "PUT",
            "api/authorizedUsers/resetPasswordAuthorizedUser",
            json_body={"id": authorized_user_id, "pin": pin},
        )

    async def update_authorized_users_order(
        self,
        account_id: int,
        ordered_ids: list[int],
    ) -> None:
        await self._request_empty(
            "PUT",
            "api/authorizedUsers/changeOrder",
            params={"accountId": account_id},
            json_body=ordered_ids,
        )

    async def get_schedule(self, account_id: int) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "api/schedules",
            params={"accountId": account_id},
        )
        return self._expect_dict(response, "schedule response")

    async def update_schedule_range(self, payload: Mapping[str, Any]) -> None:
        await self._request_empty(
            "PUT",
            "api/schedules/range",
            json_body=dict(payload),
        )

    async def set_special_schedule(self, payload: Mapping[str, Any]) -> None:
        await self._request_empty(
            "PUT",
            "api/schedules/special",
            json_body=dict(payload),
        )

    async def delete_special_schedule(self, schedule_id: int) -> None:
        await self._request_empty("DELETE", f"api/schedules/special/{schedule_id}")

    async def get_suspensions(self, external_property_id: str) -> list[dict[str, Any]]:
        response = await self._request_json(
            "GET",
            "api/mobile/suspension/v2",
            params={"externalPropertyId": external_property_id},
        )
        return self._expect_list_of_dicts(response, "suspensions")

    async def add_suspension(self, payload: Mapping[str, Any]) -> None:
        await self._request_empty(
            "POST",
            "api/mobile/suspension",
            json_body=dict(payload),
        )

    async def delete_suspension(self, event_suspension_id: int) -> None:
        await self._request_empty(
            "DELETE",
            "api/mobile/suspension",
            params={"eventSuspensionId": event_suspension_id},
        )

    async def get_contact_service_types(self) -> dict[str, Any]:
        response = await self._request_json("GET", "api/additional-contact-services")
        return self._expect_dict(response, "contact service types")

    async def get_service_types(self) -> dict[str, Any]:
        response = await self._request_json("GET", "api/v1.2/additional-services")
        return self._expect_dict(response, "service types")

    async def get_ordered_services(self, property_id: int) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            f"api/v1.2/additional-services/{property_id}",
        )
        return self._expect_dict(response, "ordered services")

    async def order_service(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = await self._request_json(
            "POST",
            "api/v1.2/additional-services",
            json_body=dict(payload),
        )
        return self._expect_dict(response, "order service response")

    async def should_show_rate_dialog(self) -> bool:
        response = await self._request_json("GET", "api/fivestars")
        if isinstance(response, bool):
            return response
        raise MySolidApiError(500, "Unexpected fivestars response", payload=response)

    async def send_app_rating(self, *, is_rated: bool) -> None:
        await self._request_empty(
            "PUT",
            "api/fivestars",
            json_body={"isRated": is_rated},
        )

    async def check_pin(self, pin: str) -> None:
        await self._request_empty("GET", f"api/pin/{pin}")

    async def update_pin(self, *, old_pin: str, new_pin: str) -> None:
        await self._request_empty(
            "PUT",
            "api/pin",
            json_body={"oldPin": old_pin, "newPin": new_pin},
        )

    async def reset_pin(self) -> None:
        await self._request_empty("PUT", "api/pin/reset")

    async def get_pin_settings(self) -> dict[str, Any]:
        response = await self._request_json("GET", "api/pinSecuredActions/pinSettings")
        return self._expect_dict(response, "pin settings")

    async def set_pin_settings(self, payload: Mapping[str, Any]) -> None:
        await self._request_empty(
            "PUT",
            "api/pinSecuredActions/pinSettings",
            json_body=dict(payload),
        )

    async def get_secured_views(self) -> dict[str, Any]:
        response = await self._request_json("GET", "api/pinSecuredActions/v2.0")
        return self._expect_dict(response, "secured views")

    async def set_secured_views(self, payload: Mapping[str, Any]) -> None:
        await self._request_empty(
            "POST",
            "api/pinSecuredActions/v2.0",
            json_body=dict(payload),
        )

    async def get_secured_view(self, action: str) -> dict[str, Any]:
        response = await self._request_json(
            "GET",
            "api/pinSecuredActions/v2.0/checkAction",
            params={"pinSecuredActionsEnum": action},
        )
        return self._expect_dict(response, "secured view response")

    async def check_secured_view_pin(self, *, action: str, pin: str) -> dict[str, Any]:
        response = await self._request_json(
            "POST",
            "api/pinSecuredActions/checkPin/v2.0",
            json_body={"pinSecuredActionsEnum": action, "pinValue": pin},
        )
        return self._expect_dict(response, "secured view pin response")

    async def get_biometric_challenge(self, *, device_id: str | None = None) -> dict[str, Any]:
        response = await self._request_json(
            "POST",
            "api/biometricAuth/challenge",
            json_body={"deviceId": device_id or self._device_id},
        )
        return self._expect_dict(response, "biometric challenge")

    async def upload_biometric_public_key(
        self,
        *,
        public_key: str,
        device_id: str | None = None,
    ) -> None:
        await self._request_empty(
            "POST",
            "api/biometricAuth",
            json_body={
                "deviceId": device_id or self._device_id,
                "publicKey": public_key,
            },
        )

    async def verify_biometric_signature(
        self,
        *,
        challenge: str,
        signature: str,
        is_auth_for_secure_view: bool,
        device_id: str | None = None,
    ) -> None:
        await self._request_empty(
            "POST",
            "api/biometricAuth/verify",
            json_body={
                "deviceId": device_id or self._device_id,
                "challenge": challenge,
                "signature": signature,
                "isAuthForSecureView": is_auth_for_secure_view,
            },
        )

    async def delete_biometric_public_key(self, *, device_id: str | None = None) -> None:
        await self._request_empty(
            "DELETE",
            f"api/biometricAuth/{device_id or self._device_id}",
        )

    async def confirm_read_notification(
        self,
        *,
        message_id: str,
        received_date: str,
    ) -> None:
        await self._request_empty(
            "POST",
            "api/firebase/confirm",
            json_body={"messageId": message_id, "receivedDate": received_date},
        )

    async def raw_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: JSON | None = None,
        authenticated: bool = True,
    ) -> JSON:
        return await self._request_json(
            method,
            path,
            params=params,
            json_body=json_body,
            authenticated=authenticated,
        )

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    def _headers(self, *, authenticated: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "CurrentAppVersionName": APP_VERSION_NAME,
            "CurrentAppVersionCode": APP_VERSION_CODE,
            "CurrentAppPhoneName": platform.system() or "Python",
            "CurrentAppPhoneVersion": self._device_name,
            "CurrentAppPhoneOsVersion": platform.release() or platform.version(),
            "CurrentAppPhoneDeviceId": self._device_id,
        }
        if self._email:
            headers["UserEmail"] = self._email
        if authenticated:
            token = self._require_token()
            headers["Authorization"] = token.value
        return headers

    def _require_token(self) -> AccessToken:
        if self._access_token is None or not self._access_token.value:
            raise MySolidSessionError("This endpoint requires an authenticated session.")
        return self._access_token

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: JSON | None = None,
        authenticated: bool = True,
    ) -> JSON:
        response = await self._request(
            method,
            path,
            params=params,
            json_body=json_body,
            authenticated=authenticated,
        )
        if response == "":
            return None
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return response

    async def _request_empty(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: JSON | None = None,
        authenticated: bool = True,
    ) -> None:
        await self._request(
            method,
            path,
            params=params,
            json_body=json_body,
            authenticated=authenticated,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: JSON | None = None,
        authenticated: bool = True,
    ) -> str:
        session = await self._ensure_session()
        url = urljoin(self._host, path)
        async with session.request(
            method.upper(),
            url,
            params=params,
            json=json_body,
            headers=self._headers(authenticated=authenticated),
        ) as response:
            text = await response.text()
            if 200 <= response.status < 300:
                return text
            payload = None
            if text:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = text
            raise self._build_error(response.status, payload)

    def _build_error(self, status: int, payload: Any | None) -> MySolidApiError:
        if isinstance(payload, Mapping) and (
            "errorCode" in payload or status in {401, 403}
        ):
            details = AuthErrorDetails(
                error_code=int(payload["errorCode"])
                if payload.get("errorCode") is not None
                else None,
                lock_time_ms=int(payload["lockTimeMs"])
                if payload.get("lockTimeMs") is not None
                else None,
            )
            message = f"Authentication failed (errorCode={details.error_code})"
            return MySolidAuthError(status, message, payload=payload, details=details)
        if status in {401, 403}:
            return MySolidAuthError(status, "Authentication failed", payload=payload)
        message = "MySolid API request failed"
        if isinstance(payload, str) and payload:
            message = payload
        return MySolidApiError(status, message, payload=payload)

    @staticmethod
    def _expect_dict(response: JSON, label: str) -> dict[str, Any]:
        if isinstance(response, Mapping):
            return dict(response)
        raise MySolidApiError(500, f"Unexpected {label}", payload=response)

    @staticmethod
    def _expect_list_of_dicts(response: JSON, label: str) -> list[dict[str, Any]]:
        if not isinstance(response, list):
            raise MySolidApiError(500, f"Unexpected {label}", payload=response)
        items: list[dict[str, Any]] = []
        for item in response:
            if not isinstance(item, Mapping):
                raise MySolidApiError(500, f"Unexpected {label}", payload=response)
            items.append(dict(item))
        return items
