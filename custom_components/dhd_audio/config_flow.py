"""Config flow for the HA DHD Audio integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_LOGIC_ID,
    CONF_LOGIC_NAME,
    CONF_LOGIC_TYPE,
    CONF_LOGICS,
    DEFAULT_PORT,
    DOMAIN,
    LOGIC_TYPE_SENSOR,
    LOGIC_TYPE_SWITCH,
)
from .ecp import DHDClient, DHDConnectionError

_LOGGER = logging.getLogger(__name__)

LOGIC_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOGIC_ID): int,
        vol.Required(CONF_LOGIC_NAME): str,
        vol.Required(
            CONF_LOGIC_TYPE, default=LOGIC_TYPE_SWITCH
        ): vol.In([LOGIC_TYPE_SENSOR, LOGIC_TYPE_SWITCH]),
    }
)


class DHDConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA DHD Audio.

    Step 1: IP + port + first logic  (single form)
    Done.  More logics can be added via Options.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup – connection + first logic in one form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            self._async_abort_entries_match({CONF_HOST: host})

            client = DHDClient(host, port)
            try:
                await client.test_connection()
            except (DHDConnectionError, OSError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                await client.disconnect()
                return self.async_create_entry(
                    title=f"HA DHD Audio ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_LOGICS: [
                            {
                                CONF_LOGIC_ID: user_input[CONF_LOGIC_ID],
                                CONF_LOGIC_NAME: user_input[CONF_LOGIC_NAME],
                                CONF_LOGIC_TYPE: user_input[CONF_LOGIC_TYPE],
                            }
                        ],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Required(CONF_LOGIC_ID): int,
                    vol.Required(CONF_LOGIC_NAME): str,
                    vol.Required(
                        CONF_LOGIC_TYPE, default=LOGIC_TYPE_SWITCH
                    ): vol.In([LOGIC_TYPE_SENSOR, LOGIC_TYPE_SWITCH]),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> DHDOptionsFlow:
        """Return the options flow handler."""
        return DHDOptionsFlow(config_entry)


class DHDOptionsFlow(OptionsFlow):
    """Handle options for HA DHD Audio.

    Uses the native HA menu with clear choices:
    - Add logic
    - Edit logic
    - Remove logic
    - Done (save & close)
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise the options flow."""
        self._config_entry = config_entry
        self._logics: list[dict[str, Any]] = list(
            config_entry.options.get(
                CONF_LOGICS,
                config_entry.data.get(CONF_LOGICS, []),
            )
        )
        self._edit_index: int | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the main menu."""
        if user_input is not None:
            action = user_input["action"]
            if action == "add_logic":
                return await self.async_step_add_logic()
            if action == "edit_logic":
                return await self.async_step_edit_logic()
            if action == "remove_logic":
                return await self.async_step_remove_logic()
            return await self.async_step_done()

        actions: dict[str, str] = {"add_logic": "Add logic"}
        if self._logics:
            actions["edit_logic"] = "Edit logic"
            actions["remove_logic"] = "Remove logic"
        actions["done"] = "Done"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required("action", default="add_logic"): vol.In(actions)}
            ),
            description_placeholders={
                "count": str(len(self._logics)),
            },
        )

    async def async_step_add_logic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new logic entity."""
        errors: dict[str, str] = {}

        if user_input is not None:
            logic_id = user_input[CONF_LOGIC_ID]

            if any(int(l[CONF_LOGIC_ID]) == logic_id for l in self._logics):
                errors[CONF_LOGIC_ID] = "logic_already_configured"
            else:
                self._logics.append(
                    {
                        CONF_LOGIC_ID: logic_id,
                        CONF_LOGIC_NAME: user_input[CONF_LOGIC_NAME],
                        CONF_LOGIC_TYPE: user_input[CONF_LOGIC_TYPE],
                    }
                )
                return await self.async_step_init()

        return self.async_show_form(
            step_id="add_logic",
            data_schema=LOGIC_SCHEMA,
            errors=errors,
        )

    async def async_step_edit_logic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which logic to edit."""
        if user_input is not None:
            edit_id = int(user_input["edit_logic_id"])
            for idx, logic in enumerate(self._logics):
                if int(logic[CONF_LOGIC_ID]) == edit_id:
                    self._edit_index = idx
                    return await self.async_step_edit_logic_detail()
            return await self.async_step_init()

        logic_choices = {
            str(l[CONF_LOGIC_ID]): f"{l[CONF_LOGIC_NAME]} (ID {l[CONF_LOGIC_ID]})"
            for l in self._logics
        }

        return self.async_show_form(
            step_id="edit_logic",
            data_schema=vol.Schema(
                {
                    vol.Required("edit_logic_id"): vol.In(logic_choices),
                }
            ),
        )

    async def async_step_edit_logic_detail(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected logic's properties."""
        assert self._edit_index is not None
        current = self._logics[self._edit_index]
        errors: dict[str, str] = {}

        if user_input is not None:
            new_id = user_input[CONF_LOGIC_ID]
            # Check duplicate (but allow keeping the same ID).
            if new_id != int(current[CONF_LOGIC_ID]) and any(
                int(l[CONF_LOGIC_ID]) == new_id for l in self._logics
            ):
                errors[CONF_LOGIC_ID] = "logic_already_configured"
            else:
                self._logics[self._edit_index] = {
                    CONF_LOGIC_ID: new_id,
                    CONF_LOGIC_NAME: user_input[CONF_LOGIC_NAME],
                    CONF_LOGIC_TYPE: user_input[CONF_LOGIC_TYPE],
                }
                self._edit_index = None
                return await self.async_step_init()

        return self.async_show_form(
            step_id="edit_logic_detail",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LOGIC_ID, default=int(current[CONF_LOGIC_ID])
                    ): int,
                    vol.Required(
                        CONF_LOGIC_NAME, default=current[CONF_LOGIC_NAME]
                    ): str,
                    vol.Required(
                        CONF_LOGIC_TYPE, default=current[CONF_LOGIC_TYPE]
                    ): vol.In([LOGIC_TYPE_SENSOR, LOGIC_TYPE_SWITCH]),
                }
            ),
            errors=errors,
        )

    async def async_step_remove_logic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove an existing logic entity."""
        if user_input is not None:
            remove_id = int(user_input["remove_logic_id"])
            self._logics = [
                l for l in self._logics if int(l[CONF_LOGIC_ID]) != remove_id
            ]
            return await self.async_step_init()

        logic_choices = {
            str(l[CONF_LOGIC_ID]): f"{l[CONF_LOGIC_NAME]} (ID {l[CONF_LOGIC_ID]})"
            for l in self._logics
        }

        return self.async_show_form(
            step_id="remove_logic",
            data_schema=vol.Schema(
                {
                    vol.Required("remove_logic_id"): vol.In(logic_choices),
                }
            ),
        )

    async def async_step_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Save and close."""
        return self.async_create_entry(
            title="",
            data={CONF_LOGICS: self._logics},
        )
