"""Setup and options, so thresholds are configured without writing automations."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    ALERT_LEVELS,
    CONF_ALERT_ENABLED,
    CONF_ALERT_MIN_LEVEL,
    CONF_ALERT_TOWN,
    CONF_FUEL_ENABLED,
    CONF_FUEL_THRESHOLD,
    CONF_FUEL_TYPES,
    CONF_HEAT_ENABLED,
    CONF_HEAT_THRESHOLD,
    CONF_NOTIFY_SERVICE,
    CONF_QUAKE_ENABLED,
    CONF_QUAKE_MIN_MAGNITUDE,
    CONF_RADIUS_FUEL,
    CONF_RADIUS_QUAKES,
    DEFAULT_FUEL_TYPES,
    DEFAULT_HEAT_THRESHOLD,
    DEFAULT_QUAKE_MIN_MAGNITUDE,
    DEFAULT_RADIUS_FUEL_KM,
    DEFAULT_RADIUS_QUAKES_KM,
    DOMAIN,
)

FUEL_TYPE_CHOICES = ["Benzina", "Gasolio", "GPL", "Metano"]


class AllerteItaliaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: what to watch, and how far around home."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Allerte Italia", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_RADIUS_FUEL, default=DEFAULT_RADIUS_FUEL_KM
                ): vol.All(vol.Coerce(float), vol.Range(min=1, max=100)),
                vol.Optional(
                    CONF_FUEL_TYPES, default=DEFAULT_FUEL_TYPES
                ): vol.All(cv_multi_select(FUEL_TYPE_CHOICES)),
                vol.Optional(
                    CONF_RADIUS_QUAKES, default=DEFAULT_RADIUS_QUAKES_KM
                ): vol.All(vol.Coerce(float), vol.Range(min=10, max=1000)),
                vol.Optional(CONF_ALERT_TOWN, default=""): str,
                vol.Optional("temperature_entity", default=""): str,
                vol.Optional("humidity_entity", default=""): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return AllerteItaliaOptionsFlow(entry)


class AllerteItaliaOptionsFlow(OptionsFlow):
    """Thresholds and the notification target."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self._entry.data, **self._entry.options}

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_NOTIFY_SERVICE,
                    default=current.get(CONF_NOTIFY_SERVICE, "notify.persistent_notification"),
                ): str,
                vol.Optional(
                    CONF_FUEL_ENABLED, default=current.get(CONF_FUEL_ENABLED, True)
                ): bool,
                vol.Optional(
                    CONF_FUEL_THRESHOLD, default=current.get(CONF_FUEL_THRESHOLD, 1.70)
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=5.0)),
                vol.Optional(
                    CONF_QUAKE_ENABLED, default=current.get(CONF_QUAKE_ENABLED, True)
                ): bool,
                vol.Optional(
                    CONF_QUAKE_MIN_MAGNITUDE,
                    default=current.get(
                        CONF_QUAKE_MIN_MAGNITUDE, DEFAULT_QUAKE_MIN_MAGNITUDE
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=8.0)),
                vol.Optional(
                    CONF_ALERT_ENABLED, default=current.get(CONF_ALERT_ENABLED, True)
                ): bool,
                vol.Optional(
                    CONF_ALERT_MIN_LEVEL,
                    default=current.get(CONF_ALERT_MIN_LEVEL, "giallo"),
                ): vol.In([level for level in ALERT_LEVELS if level != "verde"]),
                vol.Optional(
                    CONF_HEAT_ENABLED, default=current.get(CONF_HEAT_ENABLED, True)
                ): bool,
                vol.Optional(
                    CONF_HEAT_THRESHOLD,
                    default=current.get(CONF_HEAT_THRESHOLD, DEFAULT_HEAT_THRESHOLD),
                ): vol.All(vol.Coerce(float), vol.Range(min=25.0, max=50.0)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)


def cv_multi_select(options: list[str]):
    """Multi-select without importing the helper at module import time."""
    import homeassistant.helpers.config_validation as cv

    return cv.multi_select({option: option for option in options})
