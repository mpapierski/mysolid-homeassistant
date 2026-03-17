"""Camera entities for MySolid DVR channels."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MySolidRuntimeData
from .entity import MySolidCoordinatorEntity
from .models import Camera as MySolidCameraModel
from .models import CameraChannel, PropertySnapshot


@dataclass(frozen=True, slots=True)
class CameraStreamBundle:
    primary: str
    fallbacks: tuple[str, ...] = ()

    @property
    def all_sources(self) -> tuple[str, ...]:
        return (self.primary, *self.fallbacks)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime: MySolidRuntimeData = entry.runtime_data
    known: set[tuple[int, int, int]] = set()

    @callback
    def _sync_entities() -> None:
        new_entities = []
        snapshot = runtime.coordinator.data
        if snapshot is None:
            return
        for property_id, property_snapshot in snapshot.properties.items():
            for camera_index, camera in enumerate(property_snapshot.details.cameras):
                for channel_index, channel in enumerate(camera.channels):
                    key = (property_id, camera_index, channel_index)
                    if key in known:
                        continue
                    known.add(key)
                    new_entities.append(
                        MySolidCameraEntity(
                            runtime,
                            property_id,
                            camera_index,
                            channel_index,
                            camera,
                            channel,
                        )
                    )
        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()
    entry.async_on_unload(runtime.coordinator.async_add_listener(_sync_entities))


class MySolidCameraEntity(MySolidCoordinatorEntity, Camera):
    _attr_should_poll = False

    def __init__(
        self,
        runtime: MySolidRuntimeData,
        property_id: int,
        camera_index: int,
        channel_index: int,
        camera: MySolidCameraModel,
        channel: CameraChannel,
    ) -> None:
        suffix = f"camera::{camera_index}::{channel_index}"
        super().__init__(runtime, property_id, suffix)
        Camera.__init__(self)
        self._camera_index = camera_index
        self._channel_index = channel_index
        self._attr_name = channel.name or f"Camera {channel_index + 1}"
        self._attr_is_streaming = False

    @property
    def property_snapshot(self) -> PropertySnapshot:
        return self.runtime.get_property_snapshot(self.property_id)

    @property
    def camera_model(self) -> MySolidCameraModel:
        return self.property_snapshot.details.cameras[self._camera_index]

    @property
    def channel(self) -> CameraChannel:
        return self.camera_model.channels[self._channel_index]

    @property
    def available(self) -> bool:
        return build_camera_stream_bundle(self.camera_model, self._channel_index) is not None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        bundle = build_camera_stream_bundle(self.camera_model, self._channel_index)
        return {
            "serial_number": self.camera_model.serial_number,
            "address": self.camera_model.address,
            "protocol": self.camera_model.protocol,
            "channel_number": self.channel.number,
            "channel_index": self._channel_index,
            "ptz": self.channel.ptz,
            "fallback_stream_sources": list(bundle.fallbacks) if bundle else [],
        }

    async def async_stream_source(self) -> str | None:
        bundle = build_camera_stream_bundle(self.camera_model, self._channel_index)
        return bundle.primary if bundle else None


def build_camera_stream_bundle(
    camera: MySolidCameraModel,
    channel_index: int,
) -> CameraStreamBundle | None:
    if not camera.address or not camera.username or not camera.password:
        return None

    authority = _rtsp_authority(camera)
    channel_number = channel_index + 1
    protocol = (camera.protocol or "").upper()

    if protocol in {"HIKVISION", "BCSVIEW"}:
        return CameraStreamBundle(
            primary=f"rtsp://{authority}/Streaming/channels/{channel_number}01",
            fallbacks=(f"rtsp://{authority}/Streaming/channels/{channel_number}00",),
        )
    if protocol in {"DAHUA", "BCSECOLINEPROHTTP", "BCSECOLINEPROSDK"}:
        return CameraStreamBundle(
            primary=(
                f"rtsp://{authority}/cam/realmonitor?channel={channel_number}&subtype=1"
            ),
            fallbacks=(
                f"rtsp://{authority}/cam/realmonitor?channel={channel_number}&subtype=0",
            ),
        )
    if protocol in {"UNIVIEW", "BCSPOINTIP"}:
        return CameraStreamBundle(
            primary=f"rtsp://{authority}/unicast/c{channel_number}/s1/",
            fallbacks=(f"rtsp://{authority}/unicast/c{channel_number}/s0/",),
        )
    return None


def _rtsp_authority(camera: MySolidCameraModel) -> str:
    rtsp_port = camera.rtsp_port or camera.port or "554"
    password = quote(camera.password or "", safe="")
    return f"{camera.username}:{password}@{camera.address}:{rtsp_port}"
