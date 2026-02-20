"""DHD External Control Protocol (ECP) TCP client.

Implements the binary protocol for communicating with DHD audio mixing
consoles over TCP port 2008.  Each message is a fixed 16-byte block:

    Byte  0      : data length (0-8)
    Byte  1      : reserved (0x00)
    Bytes 2-5    : 32-bit command ID, MSB first
    Bytes 6-13   : data bytes (0-8), padded with 0x00
    Bytes 14-15  : reserved (0x00, 0x00)

Reference: https://developer.dhd.audio/docs/API/ECP/communication
"""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import Any

from .const import ECP_BLOCK_SIZE, ECP_CMD_SET_LOGIC

_LOGGER = logging.getLogger(__name__)

# Timeout for TCP operations in seconds.
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 5


class DHDProtocolError(Exception):
    """Raised when the DHD device returns an unexpected response."""


class DHDConnectionError(Exception):
    """Raised when the connection to the DHD device fails."""


class DHDClient:
    """Async TCP client for the DHD ECP protocol.

    Runs a background listener that reads all incoming blocks from the
    mixer.  Unsolicited logic state-change notifications are dispatched
    via an optional callback, enabling instant push updates.
    """

    def __init__(self, host: str, port: int) -> None:
        """Initialise the client.

        Args:
            host: IP address or hostname of the DHD device.
            port: TCP port (default 2008).

        """
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

        # Background listener
        self._listener_task: asyncio.Task[None] | None = None

        # Pending command responses: the listener routes matching blocks here.
        self._pending: dict[
            int, asyncio.Future[tuple[int, bytes]]
        ] = {}
        self._pending_id: int = 0

        # Callback for unsolicited logic state-change notifications.
        # Signature: callback(logic_id: int, state: bool) -> None
        self._logic_callback: Any = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def host(self) -> str:
        """Return the configured host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the configured port."""
        return self._port

    @property
    def connected(self) -> bool:
        """Return True when the TCP socket is open."""
        return self._writer is not None and not self._writer.is_closing()

    def set_logic_callback(self, callback: Any) -> None:
        """Register a callback for unsolicited logic state changes.

        Args:
            callback: Callable(logic_id: int, state: bool) -> None.

        """
        self._logic_callback = callback

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open a TCP connection and start the background listener."""
        if self.connected:
            return

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=CONNECT_TIMEOUT,
            )
            _LOGGER.debug(
                "Connected to DHD mixer at %s:%s", self._host, self._port
            )
        except (OSError, asyncio.TimeoutError) as err:
            self._reader = None
            self._writer = None
            raise DHDConnectionError(
                f"Failed to connect to {self._host}:{self._port}"
            ) from err

        self._start_listener()

    async def disconnect(self) -> None:
        """Stop the listener and close the TCP connection."""
        self._stop_listener()

        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            finally:
                self._writer = None
                self._reader = None
                _LOGGER.debug(
                    "Disconnected from DHD mixer at %s:%s",
                    self._host,
                    self._port,
                )

    async def _ensure_connected(self) -> None:
        """Reconnect if the socket was closed."""
        if not self.connected:
            await self.connect()

    # ------------------------------------------------------------------
    # Background listener
    # ------------------------------------------------------------------

    def _start_listener(self) -> None:
        """Start the background listener task."""
        if self._listener_task is not None and not self._listener_task.done():
            return
        self._listener_task = asyncio.ensure_future(self._listener_loop())

    def _stop_listener(self) -> None:
        """Cancel the background listener task."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            self._listener_task = None
        # Fail any pending futures.
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(DHDConnectionError("Disconnected"))
        self._pending.clear()

    async def _listener_loop(self) -> None:
        """Continuously read blocks and dispatch them."""
        assert self._reader is not None
        try:
            while True:
                try:
                    raw = await self._reader.readexactly(ECP_BLOCK_SIZE)
                except asyncio.IncompleteReadError:
                    _LOGGER.warning("Connection lost to DHD mixer")
                    break

                length, cmd, data = self._parse_block(raw)
                _LOGGER.debug(
                    "RX ← 0x%08X  data=%s", cmd, data.hex(),
                )

                # Try to deliver to a pending command first.
                delivered = False
                for pid, fut in list(self._pending.items()):
                    if fut.done():
                        continue
                    # Check if this block matches the pending request.
                    expected_cmd, expected_logic = fut._dhd_match  # type: ignore[attr-defined]
                    if cmd != expected_cmd:
                        continue
                    if expected_logic is not None and len(data) >= 2:
                        resp_logic = int.from_bytes(data[:2], "big")
                        if resp_logic != expected_logic:
                            continue
                    fut.set_result((cmd, data))
                    delivered = True
                    break

                # If not delivered to a pending command, treat as push.
                if not delivered and cmd == ECP_CMD_SET_LOGIC and len(data) >= 3:
                    logic_id = int.from_bytes(data[:2], "big")
                    state = data[2] != 0x00
                    _LOGGER.debug(
                        "Push update: logic %d = %s", logic_id, state,
                    )
                    if self._logic_callback is not None:
                        try:
                            self._logic_callback(logic_id, state)
                        except Exception:
                            _LOGGER.exception("Error in logic callback")

        except asyncio.CancelledError:
            return
        except Exception:
            _LOGGER.exception("Listener loop crashed")

    # ------------------------------------------------------------------
    # Low-level protocol helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_block(command_id: int, data: bytes) -> bytes:
        """Build a 16-byte ECP block.

        Args:
            command_id: 32-bit command identifier.
            data: Payload bytes (0-8 bytes).

        Returns:
            A 16-byte ``bytes`` object ready to send over TCP.

        Raises:
            ValueError: If *data* exceeds 8 bytes.

        """
        if len(data) > 8:
            raise ValueError(f"ECP data must be ≤ 8 bytes, got {len(data)}")

        padded_data = data.ljust(8, b"\x00")

        block = struct.pack(
            ">BB4s8sBB",
            len(data),       # byte 0  – length
            0x00,            # byte 1  – reserved
            command_id.to_bytes(4, "big"),  # bytes 2-5 – command ID
            padded_data,     # bytes 6-13 – data
            0x00,            # byte 14 – reserved
            0x00,            # byte 15 – reserved
        )
        return block

    @staticmethod
    def _parse_block(block: bytes) -> tuple[int, int, bytes]:
        """Parse a 16-byte ECP block.

        Returns:
            Tuple of (length, command_id, data).

        Raises:
            DHDProtocolError: If the block is not exactly 16 bytes.

        """
        if len(block) != ECP_BLOCK_SIZE:
            raise DHDProtocolError(
                f"Expected {ECP_BLOCK_SIZE}-byte block, got {len(block)}"
            )

        length = block[0]
        command_id = int.from_bytes(block[2:6], "big")
        data = block[6 : 6 + length]
        return length, command_id, data

    # ------------------------------------------------------------------
    # Send / receive (via listener)
    # ------------------------------------------------------------------

    async def send_command(
        self, command_id: int, data: bytes, logic_id: int | None = None
    ) -> tuple[int, bytes]:
        """Send a command and return the matching response.

        The background listener routes the matching response block back
        to this caller via an ``asyncio.Future``.

        Args:
            command_id: 32-bit ECP command.
            data: Payload bytes (0-8).
            logic_id: If set, match the response logic ID as well.

        Returns:
            Tuple of (response_command_id, response_data).

        """
        async with self._lock:
            await self._ensure_connected()
            assert self._writer is not None

            # Create a future for the listener to fill.
            self._pending_id += 1
            pid = self._pending_id
            loop = asyncio.get_running_loop()
            fut: asyncio.Future[tuple[int, bytes]] = loop.create_future()
            fut._dhd_match = (command_id, logic_id)  # type: ignore[attr-defined]
            self._pending[pid] = fut

            block = self._build_block(command_id, data)
            _LOGGER.debug(
                "TX → 0x%08X  data=%s", command_id, data.hex(),
            )
            self._writer.write(block)
            await self._writer.drain()

            try:
                return await asyncio.wait_for(fut, timeout=READ_TIMEOUT)
            except asyncio.TimeoutError as err:
                raise DHDProtocolError(
                    f"Timeout waiting for response to 0x{command_id:08X}"
                ) from err
            finally:
                self._pending.pop(pid, None)

    # ------------------------------------------------------------------
    # High-level logic helpers
    # ------------------------------------------------------------------

    async def get_logic_state(self, logic_id: int) -> bool:
        """Query the current state of an internal logic.

        The query is sent with 2 data bytes (logic ID, big-endian).
        The response carries 3 data bytes: logic ID (2 bytes) + state (1 byte).

        Args:
            logic_id: 16-bit logic number as configured in Toolbox.

        Returns:
            ``True`` if the logic is active, ``False`` otherwise.

        """
        data = logic_id.to_bytes(2, "big")
        _, resp_data = await self.send_command(
            ECP_CMD_SET_LOGIC, data, logic_id=logic_id
        )

        if len(resp_data) < 3:
            raise DHDProtocolError(
                f"Unexpected response length {len(resp_data)} for logic query"
            )

        return resp_data[2] != 0x00

    async def set_logic_state(self, logic_id: int, state: bool) -> None:
        """Set an internal logic to on or off.

        Sends 3 data bytes: logic ID (2 bytes, big-endian) + state (1 byte).
        Reads the confirmation response to keep the TCP buffer clean.

        Args:
            logic_id: 16-bit logic number as configured in Toolbox.
            state: ``True`` to activate, ``False`` to deactivate.

        """
        data = logic_id.to_bytes(2, "big") + (b"\x01" if state else b"\x00")
        await self.send_command(
            ECP_CMD_SET_LOGIC, data, logic_id=logic_id
        )

    async def test_connection(self) -> bool:
        """Test connectivity by opening (and keeping) the TCP socket.

        Returns:
            ``True`` if the connection succeeds.

        Raises:
            DHDConnectionError: If the connection fails.

        """
        await self._ensure_connected()
        return True
