"""The Allerte Italia integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN
from .coordinator import build_coordinators
from .notifications import NotificationManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Configured from the UI only, never from YAML.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start one coordinator per enabled source."""
    coordinators = build_coordinators(hass, entry)
    notifier = NotificationManager(hass, {**entry.data, **entry.options})

    for name, coordinator in coordinators.items():
        coordinator.async_add_listener(
            _make_listener(hass, notifier, name, coordinator)
        )
        # A source that fails its first refresh must not abort the setup of the
        # others: the coordinator records the failure and its entities show as
        # unavailable.
        await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinators": coordinators,
        "notifier": notifier,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear down the platforms and forget the coordinators."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed: rebuild everything with the new thresholds."""
    await hass.config_entries.async_reload(entry.entry_id)


def _make_listener(hass, notifier, name, coordinator):
    """Feed each refresh to the notification manager."""

    def _listener() -> None:
        data = coordinator.data
        if data is None:
            return
        hass.async_create_task(notifier.async_process(name, data))

    return _listener
