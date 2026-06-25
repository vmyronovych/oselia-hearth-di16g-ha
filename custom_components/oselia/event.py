"""`event` entity per switch input -- fires on single/double/long gestures.

Input count comes from the gateway's diag/state `boards` (x16); entities are added as
boards become known (SIGNAL_NEW_INPUTS) and never removed if the count dips.
"""
from __future__ import annotations

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OseliaConfigEntry
from .client import Gateway, OseliaClient
from .const import (
    GESTURES,
    PINS_PER_CHIP,
    SIGNAL_ACTION,
    SIGNAL_NEW_GATEWAY,
    SIGNAL_NEW_INPUTS,
)
from .entity import OseliaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OseliaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = entry.runtime_data
    created: set[tuple[str, int, int]] = set()

    @callback  # @callback so the dispatcher runs it on the loop, not in an executor.
    def _add_inputs(device_id: str, boards: int) -> None:
        gw = client.gateways[device_id]
        new: list[OseliaInputEvent] = []
        for board in range(1, boards + 1):
            for pin in range(1, PINS_PER_CHIP + 1):
                key = (device_id, board, pin)
                if key in created:
                    continue
                created.add(key)
                new.append(OseliaInputEvent(client, gw, board, pin))
        if new:
            async_add_entities(new)

    @callback
    def _on_new_gateway(device_id: str) -> None:
        gw = client.gateways[device_id]
        if gw.boards:
            _add_inputs(device_id, gw.boards)

        @callback  # nested @callback closure (not a lambda) so the marker is preserved.
        def _inputs_changed(boards: int) -> None:
            _add_inputs(device_id, boards)

        entry.async_on_unload(
            async_dispatcher_connect(
                hass, SIGNAL_NEW_INPUTS.format(device_id), _inputs_changed
            )
        )

    for device_id in list(client.gateways):
        _on_new_gateway(device_id)
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_GATEWAY, _on_new_gateway)
    )


class OseliaInputEvent(OseliaEntity, EventEntity):
    """One wall-switch input as an HA event entity."""

    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = list(GESTURES)
    _attr_icon = "mdi:gesture-tap-button"

    def __init__(
        self, client: OseliaClient, gateway: Gateway, board: int, pin: int
    ) -> None:
        super().__init__(client, gateway)
        self._board = board
        self._pin = pin
        self._attr_name = f"Board {board} input {pin}"
        self._attr_unique_id = (
            f"hearth_{gateway.device_id}_b{board}_in{pin}_event"
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ACTION.format(self._gw.device_id),
                self._on_action,
            )
        )

    @callback
    def _on_action(self, board: int, pin: int, gesture: str) -> None:
        if board != self._board or pin != self._pin:
            return
        if gesture not in GESTURES:
            return
        self._trigger_event(gesture)
        self.async_write_ha_state()
