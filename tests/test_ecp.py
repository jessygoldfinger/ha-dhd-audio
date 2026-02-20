"""Tests for the DHD ECP protocol client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.dhd_audio.ecp import (
    DHDClient,
    DHDConnectionError,
    DHDProtocolError,
    ECP_BLOCK_SIZE,
)


class TestBuildBlock:
    """Tests for DHDClient._build_block."""

    def test_block_is_16_bytes(self) -> None:
        """A built block must always be exactly 16 bytes."""
        block = DHDClient._build_block(0x110E0000, b"\x00\x01")
        assert len(block) == ECP_BLOCK_SIZE

    def test_length_byte(self) -> None:
        """Byte 0 must equal the length of the supplied data."""
        block = DHDClient._build_block(0x110E0000, b"\x00\x01\x01")
        assert block[0] == 3

    def test_reserved_byte_1(self) -> None:
        """Byte 1 must be 0x00."""
        block = DHDClient._build_block(0x110E0000, b"\x00\x01")
        assert block[1] == 0x00

    def test_command_id_encoding(self) -> None:
        """Bytes 2-5 must contain the command ID in big-endian."""
        block = DHDClient._build_block(0x110E0000, b"")
        assert block[2:6] == b"\x11\x0E\x00\x00"

    def test_data_padded_to_8_bytes(self) -> None:
        """Data region (bytes 6-13) is padded with 0x00."""
        block = DHDClient._build_block(0x110E0000, b"\xAB")
        assert block[6] == 0xAB
        assert block[7:14] == b"\x00" * 7

    def test_trailing_reserved_bytes(self) -> None:
        """Bytes 14-15 must be 0x00."""
        block = DHDClient._build_block(0x110E0000, b"\x01\x02")
        assert block[14] == 0x00
        assert block[15] == 0x00

    def test_data_too_long_raises(self) -> None:
        """Data longer than 8 bytes must raise ValueError."""
        with pytest.raises(ValueError, match="8 bytes"):
            DHDClient._build_block(0x110E0000, b"\x00" * 9)

    def test_empty_data(self) -> None:
        """An empty data payload is valid."""
        block = DHDClient._build_block(0x110E0000, b"")
        assert block[0] == 0
        assert len(block) == ECP_BLOCK_SIZE


class TestParseBlock:
    """Tests for DHDClient._parse_block."""

    def test_round_trip(self) -> None:
        """Building and parsing a block must yield the original values."""
        cmd = 0x110E0000
        data = b"\x00\x42\x01"
        block = DHDClient._build_block(cmd, data)
        length, parsed_cmd, parsed_data = DHDClient._parse_block(block)
        assert length == len(data)
        assert parsed_cmd == cmd
        assert parsed_data == data

    def test_wrong_size_raises(self) -> None:
        """A block that is not 16 bytes must raise DHDProtocolError."""
        with pytest.raises(DHDProtocolError):
            DHDClient._parse_block(b"\x00" * 10)


class TestLogicStateEncoding:
    """Verify the high-level logic helpers build correct payloads."""

    @pytest.mark.asyncio
    async def test_set_logic_on(self) -> None:
        """set_logic_state(id, True) must send 3 bytes: ID_hi, ID_lo, 0x01."""
        client = DHDClient("127.0.0.1", 2008)
        client.send_command = AsyncMock(
            return_value=(0x110E0000, b"\x00\x42\x01")
        )

        await client.set_logic_state(0x0042, True)

        client.send_command.assert_awaited_once_with(
            0x110E0000, b"\x00\x42\x01", logic_id=0x0042
        )

    @pytest.mark.asyncio
    async def test_set_logic_off(self) -> None:
        """set_logic_state(id, False) must send 3 bytes: ID_hi, ID_lo, 0x00."""
        client = DHDClient("127.0.0.1", 2008)
        client.send_command = AsyncMock(
            return_value=(0x110E0000, b"\x00\x42\x00")
        )

        await client.set_logic_state(0x0042, False)

        client.send_command.assert_awaited_once_with(
            0x110E0000, b"\x00\x42\x00", logic_id=0x0042
        )

    @pytest.mark.asyncio
    async def test_get_logic_state_true(self) -> None:
        """get_logic_state must return True when response byte is non-zero."""
        client = DHDClient("127.0.0.1", 2008)
        client.send_command = AsyncMock(
            return_value=(0x110E0000, b"\x00\x42\x01")
        )

        result = await client.get_logic_state(0x0042)
        assert result is True
        client.send_command.assert_awaited_once_with(
            0x110E0000, b"\x00\x42", logic_id=0x0042
        )

    @pytest.mark.asyncio
    async def test_get_logic_state_false(self) -> None:
        """get_logic_state must return False when response byte is 0x00."""
        client = DHDClient("127.0.0.1", 2008)
        client.send_command = AsyncMock(
            return_value=(0x110E0000, b"\x00\x42\x00")
        )

        result = await client.get_logic_state(0x0042)
        assert result is False
        client.send_command.assert_awaited_once_with(
            0x110E0000, b"\x00\x42", logic_id=0x0042
        )

    @pytest.mark.asyncio
    async def test_get_logic_short_response_raises(self) -> None:
        """get_logic_state must raise on a response shorter than 3 bytes."""
        client = DHDClient("127.0.0.1", 2008)
        client.send_command = AsyncMock(
            return_value=(0x110E0000, b"\x00\x42")
        )

        with pytest.raises(DHDProtocolError):
            await client.get_logic_state(0x0042)


class TestConnection:
    """Tests for connect / disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """A successful connection sets the reader and writer."""
        client = DHDClient("127.0.0.1", 2008)

        mock_reader = MagicMock(spec=asyncio.StreamReader)
        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False

        with patch(
            "custom_components.dhd_audio.ecp.asyncio.open_connection",
            return_value=(mock_reader, mock_writer),
        ):
            await client.connect()

        assert client.connected is True

    @pytest.mark.asyncio
    async def test_connect_failure_raises(self) -> None:
        """A connection failure must raise DHDConnectionError."""
        client = DHDClient("192.0.2.1", 2008)

        with patch(
            "custom_components.dhd_audio.ecp.asyncio.open_connection",
            side_effect=OSError("Connection refused"),
        ):
            with pytest.raises(DHDConnectionError):
                await client.connect()

        assert client.connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """After disconnect, connected must be False."""
        client = DHDClient("127.0.0.1", 2008)

        mock_reader = MagicMock(spec=asyncio.StreamReader)
        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False
        mock_writer.wait_closed = AsyncMock()

        with patch(
            "custom_components.dhd_audio.ecp.asyncio.open_connection",
            return_value=(mock_reader, mock_writer),
        ):
            await client.connect()

        await client.disconnect()
        assert client.connected is False

    @pytest.mark.asyncio
    async def test_double_connect_is_noop(self) -> None:
        """Calling connect() when already connected does nothing."""
        client = DHDClient("127.0.0.1", 2008)

        mock_reader = MagicMock(spec=asyncio.StreamReader)
        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.is_closing.return_value = False

        with patch(
            "custom_components.dhd_audio.ecp.asyncio.open_connection",
            return_value=(mock_reader, mock_writer),
        ) as mock_open:
            await client.connect()
            await client.connect()

        mock_open.assert_awaited_once()
