"""DataUpdateCoordinator for the HA DHD Audio integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_LOGICS,
    CONF_LOGIC_ID,
    DOMAIN,
)
from .ecp import DHDClient, DHDConnectionError, DHDProtocolError

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=10)


class DHDCoordinator(DataUpdateCoordinator[dict[int, bool]]):
    """Coordinator that receives push updates from a DHD mixer.

    The ECP client's background listener dispatches unsolicited logic
    state-change notifications via a callback.  This coordinator
    updates ``self.data`` instantly and notifies all entities.

    A 10-second poll interval ensures automatic reconnection when the
    mixer has been powered off and comes back online.
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: DHDClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=POLL_INTERVAL,
        )
        self.client = client
        self.config_entry = entry

        # Register the push callback on the ECP client.
        self.client.set_logic_callback(self._handle_logic_push)

    def _get_logic_ids(self) -> list[int]:
        """Return the list of logic IDs from the config entry options/data."""
        logics: list[dict[str, Any]] = self.config_entry.options.get(
            CONF_LOGICS,
            self.config_entry.data.get(CONF_LOGICS, []),
        )
        return [int(logic[CONF_LOGIC_ID]) for logic in logics]

    @callback
    def _handle_logic_push(self, logic_id: int, state: bool) -> None:
        """Handle an unsolicited logic state change from the mixer."""
        tracked = self._get_logic_ids()
        if logic_id not in tracked:
            return

        if self.data is None:
            self.data = {}

        if self.data.get(logic_id) == state:
            return

        _LOGGER.debug(
            "Instant update: logic %d → %s", logic_id, state,
        )
        self.data[logic_id] = state
        self.async_set_updated_data(self.data)

    async def _async_update_data(self) -> dict[int, bool]:
        """Fetch the current state of all configured logics.

        Called every 10 seconds.  If the connection is down, attempts
        to reconnect before querying.
        """
        logic_ids = self._get_logic_ids()

        if not logic_ids:
            return {}

        # Reconnect if the connection was lost.
        if not self.client.connected:
            _LOGGER.debug("Connection lost, attempting reconnect...")
            try:
                await self.client.disconnect()
                await self.client.connect()
                _LOGGER.info("Reconnected to DHD mixer")
            except (DHDConnectionError, OSError, TimeoutError) as err:
                raise UpdateFailed(
                    f"Cannot reconnect to DHD mixer: {err}"
                ) from err

        states: dict[int, bool] = {}

        try:
            for logic_id in logic_ids:
                states[logic_id] = await self.client.get_logic_state(logic_id)
        except DHDConnectionError as err:
            await self.client.disconnect()
            raise UpdateFailed(
                f"Lost connection to DHD mixer: {err}"
            ) from err
        except DHDProtocolError as err:
            raise UpdateFailed(
                f"Protocol error from DHD mixer: {err}"
            ) from err

        return states
