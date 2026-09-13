"""
The asyncio TCP server. Speaks RESP, so it's compatible with redis-cli
and any standard Redis client library out of the box.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .commands import COMMANDS
from .resp import ProtocolError, RespError, encode, read_command
from .store import Store

log = logging.getLogger("miniredis")


class MiniRedisServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6380,
        snapshot_path: Optional[str] = "dump.mrdb",
        save_interval: float = 30.0,
    ):
        self.host = host
        self.port = port
        self.store = Store(snapshot_path=snapshot_path)
        self.save_interval = save_interval
        self._server: Optional[asyncio.base_events.Server] = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        if self.save_interval and self.store.snapshot_path:
            asyncio.create_task(self._autosave_loop())
        addrs = ", ".join(str(sock.getsockname()) for sock in self._server.sockets)
        log.info("mini-redis listening on %s", addrs)
        async with self._server:
            await self._server.serve_forever()

    async def _autosave_loop(self) -> None:
        while True:
            await asyncio.sleep(self.save_interval)
            self.store.save()
            log.debug("autosave complete")

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        log.info("client connected: %s", peer)
        try:
            while True:
                try:
                    parts = await read_command(reader)
                except (ProtocolError, asyncio.IncompleteReadError):
                    writer.write(encode(RespError("ERR Protocol error")))
                    await writer.drain()
                    break

                if parts is None:
                    break  # client disconnected
                if not parts:
                    continue

                name, *args = parts
                reply = self._dispatch(name, args)
                writer.write(encode(reply))
                await writer.drain()

                if name.upper() == "SHUTDOWN":
                    self.store.save()
                    writer.close()
                    return
        finally:
            writer.close()
            log.info("client disconnected: %s", peer)

    def _dispatch(self, name: str, args):
        handler = COMMANDS.get(name.upper())
        if handler is None:
            return RespError(f"ERR unknown command '{name}'")
        try:
            return handler(self.store, args)
        except RespError as exc:
            return exc
        except Exception as exc:  # keep the server alive on bad input
            log.exception("error handling command %s", name)
            return RespError(f"ERR {exc}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="mini-redis server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6380)
    parser.add_argument("--snapshot", default="dump.mrdb")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    server = MiniRedisServer(
        host=args.host,
        port=args.port,
        snapshot_path=None if args.no_persist else args.snapshot,
    )
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        server.store.save()
        log.info("shutting down, snapshot saved")


if __name__ == "__main__":
    main()
