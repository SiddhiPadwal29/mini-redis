import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from miniredis.resp import OK, RespError, encode, read_command


def test_encode_simple_string():
    assert encode(OK) == b"+OK\r\n"


def test_encode_integer():
    assert encode(42) == b":42\r\n"


def test_encode_bulk_string():
    assert encode("hello") == b"$5\r\nhello\r\n"


def test_encode_nil():
    assert encode(None) == b"$-1\r\n"


def test_encode_array():
    assert encode(["a", "b"]) == b"*2\r\n$1\r\na\r\n$1\r\nb\r\n"


def test_encode_error():
    assert encode(RespError("ERR bad")) == b"-ERR bad\r\n"


async def _read_from(data: bytes):
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return await read_command(reader)


def test_read_command_array():
    raw = b"*3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n"
    parts = asyncio.run(_read_from(raw))
    assert parts == ["SET", "foo", "bar"]


def test_read_command_inline():
    parts = asyncio.run(_read_from(b"PING\r\n"))
    assert parts == ["PING"]


def test_read_command_eof():
    parts = asyncio.run(_read_from(b""))
    assert parts is None
