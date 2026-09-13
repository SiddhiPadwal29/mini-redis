"""
RESP (REdis Serialization Protocol) encoding and decoding.

This module implements just enough of RESP2 to talk to real Redis
clients, including redis-cli and redis-py, over a plain TCP socket.

Wire format reference:
    +OK\r\n                  -> Simple string
    -ERR message\r\n         -> Error
    :1000\r\n                -> Integer
    $6\r\nfoobar\r\n         -> Bulk string
    $-1\r\n                  -> Null bulk string
    *2\r\n$3\r\nfoo\r\n$3\r\nbar\r\n  -> Array
    *-1\r\n                  -> Null array
"""
from __future__ import annotations

import asyncio
from typing import Any, List, Optional, Union

RespValue = Union[str, int, bytes, list, None, "RespError"]


class RespError(Exception):
    """Wraps an error message that should be sent back as a RESP error."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ProtocolError(Exception):
    """Raised when the client sends malformed RESP data."""


async def read_command(reader: asyncio.StreamReader) -> Optional[List[str]]:
    """
    Read one full command from the client as a list of string arguments.

    Real clients (redis-cli, redis-py, etc.) send commands as RESP
    arrays of bulk strings, e.g. SET foo bar becomes:
        *3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n

    Returns None on a clean disconnect (EOF before any data).
    """
    line = await reader.readline()
    if not line:
        return None  # client closed the connection

    line = line.rstrip(b"\r\n")
    if not line:
        return []

    if line.startswith(b"*"):
        return await _read_array(reader, line)

    # Fallback: inline command (space separated), mostly useful for
    # quick manual testing with `nc` / telnet.
    return line.decode("utf-8", errors="replace").split()


async def _read_array(reader: asyncio.StreamReader, header: bytes) -> List[str]:
    try:
        count = int(header[1:])
    except ValueError as exc:
        raise ProtocolError(f"invalid multibulk length: {header!r}") from exc

    if count <= 0:
        return []

    args: List[str] = []
    for _ in range(count):
        type_line = await reader.readline()
        type_line = type_line.rstrip(b"\r\n")
        if not type_line.startswith(b"$"):
            raise ProtocolError(f"expected bulk string, got {type_line!r}")

        length = int(type_line[1:])
        if length == -1:
            args.append(None)  # type: ignore[arg-type]
            continue

        data = await reader.readexactly(length)
        await reader.readexactly(2)  # trailing \r\n
        args.append(data.decode("utf-8", errors="replace"))

    return args


def encode(value: RespValue) -> bytes:
    """Encode a Python value into a RESP-formatted byte string."""
    if isinstance(value, RespError):
        return f"-{value.message}\r\n".encode()
    if value is None:
        return b"$-1\r\n"
    if isinstance(value, bool):
        # bool is an int subclass in Python; guard against surprises.
        return f":{int(value)}\r\n".encode()
    if isinstance(value, int):
        return f":{value}\r\n".encode()
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        parts = [f"*{len(items)}\r\n".encode()]
        for item in items:
            parts.append(encode(item))
        return b"".join(parts)
    if isinstance(value, SimpleString):
        return f"+{value}\r\n".encode()
    # Default: treat as a bulk string.
    text = str(value)
    data = text.encode("utf-8")
    return f"${len(data)}\r\n".encode() + data + b"\r\n"


class SimpleString(str):
    """Marker type so we can distinguish '+OK' replies from bulk strings."""


OK = SimpleString("OK")
