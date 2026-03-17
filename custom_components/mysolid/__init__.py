"""MySolid Home Assistant integration."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Mapping
from types import ModuleType
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.importlib import async_import_module

from .const import DOMAIN, PLATFORMS

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
_MODULE_CACHE: dict[str, ModuleType] = {}


def build_runtime(hass: HomeAssistant, entry: ConfigEntry):
    module = _sync_import_module("coordinator")
    return module.build_runtime(hass, entry)


def _sync_import_module(name: str) -> ModuleType:
    if module := _MODULE_CACHE.get(name):
        return module
    module = importlib.import_module(f"{__package__}.{name}")
    _MODULE_CACHE[name] = module
    return module


async def _async_import_integration_module(
    hass: HomeAssistant,
    name: str,
) -> ModuleType:
    module = await async_import_module(hass, f"{__package__}.{name}")
    _MODULE_CACHE[name] = module
    return module


async def async_setup(hass: HomeAssistant, config: Mapping[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {})
    services_module = await _async_import_integration_module(hass, "services")
    await services_module.async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await _async_import_integration_module(hass, "coordinator")
    runtime = build_runtime(hass, entry)
    await runtime.async_initialize()
    entry.runtime_data = runtime
    hass.data[DOMAIN][entry.entry_id] = runtime
    await asyncio.gather(
        *(_async_import_integration_module(hass, platform) for platform in PLATFORMS)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    runtime = hass.data[DOMAIN].pop(entry.entry_id)
    await runtime.async_shutdown()
    if not hass.data[DOMAIN]:
        services_module = await _async_import_integration_module(hass, "services")
        services_module.async_unregister_services(hass)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    storage_module = await _async_import_integration_module(hass, "storage")
    await storage_module.MySolidStateStore(hass, entry.entry_id).async_remove()
