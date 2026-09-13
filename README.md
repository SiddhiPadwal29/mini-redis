# mini-redis

A small, dependency-free Redis server implementation in Python, built from
scratch on top of `asyncio`. It speaks real RESP (the Redis wire protocol),
so it works with `redis-cli` and standard Redis client libraries like
`redis-py` — no custom client needed.

Built as a learning project to understand how Redis actually works under
the hood: the wire protocol, an in-memory data store with TTL-based
expiration, and a minimal persistence layer.

## Features

- **RESP2 protocol** — parses and encodes simple strings, errors, integers,
  bulk strings, and arrays, matching real Redis wire format.
- **Data types** — strings, lists, hashes, and sets.
- **Key expiration** — `EXPIRE` / `TTL` / `PERSIST`, with both lazy
  (on-access) and active (background) expiry.
- **Persistence** — snapshot the dataset to disk with `SAVE`, auto-save on
  an interval, and reload on startup.
- **~30 commands** across strings, lists, hashes, sets, and key management.
- **Async, single-process** server using `asyncio.start_server`, so it
  handles many concurrent connections without threads.
- **Tested** — unit tests for the protocol layer and every command.

## Supported commands

| Category | Commands |
|---|---|
| Connection | `PING`, `ECHO` |
| Strings | `SET` (with `EX`/`PX`), `GET`, `APPEND`, `INCR`, `DECR`, `INCRBY` |
| Keys | `DEL`, `EXISTS`, `EXPIRE`, `TTL`, `PERSIST`, `TYPE`, `KEYS`, `DBSIZE`, `FLUSHALL` |
| Lists | `LPUSH`, `RPUSH`, `LPOP`, `RPOP`, `LLEN`, `LRANGE` |
| Hashes | `HSET`, `HGET`, `HGETALL`, `HDEL`, `HKEYS`, `HVALS` |
| Sets | `SADD`, `SREM`, `SMEMBERS`, `SISMEMBER` |
| Persistence | `SAVE`, `SHUTDOWN` |

## Getting started

Requires Python 3.9+. No third-party dependencies to run the server itself.

```bash
git clone https://github.com/<your-username>/mini-redis.git
cd mini-redis
python main.py --port 6380
```

Then, from another terminal, talk to it with the real `redis-cli`:

```bash
redis-cli -p 6380
127.0.0.1:6380> SET foo bar
OK
127.0.0.1:6380> GET foo
"bar"
127.0.0.1:6380> RPUSH mylist a b c
(integer) 3
127.0.0.1:6380> LRANGE mylist 0 -1
1) "a"
2) "b"
3) "c"
127.0.0.1:6380> EXPIRE foo 30
(integer) 1
127.0.0.1:6380> TTL foo
(integer) 30
```

Or use any standard client library, e.g. `redis-py`:

```python
import redis

r = redis.Redis(host="localhost", port=6380)
r.set("foo", "bar")
print(r.get("foo"))  # b"bar"
```

### CLI options

```
python main.py --host 127.0.0.1 --port 6380 --snapshot dump.mrdb
python main.py --no-persist          # run purely in-memory, no snapshot file
python main.py -v                    # verbose logging
```

## Running tests

```bash
pip install -r requirements.txt
pytest -v
```

## Project structure

```
mini-redis/
├── main.py                # entry point
├── miniredis/
│   ├── resp.py             # RESP protocol encode/decode
│   ├── store.py            # in-memory key/value store + TTL + snapshotting
│   ├── commands.py         # command implementations (SET, LPUSH, HSET, ...)
│   └── server.py           # asyncio TCP server tying it together
└── tests/
    ├── test_resp.py
    └── test_store.py
```

## How it works

1. **`resp.py`** reads raw bytes off the socket and turns them into a list
   of string arguments — the same format `redis-cli` sends on the wire —
   and encodes Python values back into RESP replies.
2. **`store.py`** holds all keys in a single dict guarded by a lock, with
   each entry carrying an optional expiry timestamp. Expired keys are
   swept both lazily (when touched) and periodically.
3. **`commands.py`** is a simple registry: each Redis command is a small
   function that reads/writes the store and returns a plain Python value
   (str, int, list, None, or an error) for `resp.py` to encode.
4. **`server.py`** accepts connections with `asyncio.start_server`, reads
   one command at a time per connection, dispatches it, and writes the
   reply back — all without blocking other clients.

## Limitations

This is an educational project, not a production datastore. Notable gaps
compared to real Redis: no RDB/AOF-compatible file format (snapshots use
`pickle`), no replication or clustering, no pub/sub, no Lua scripting, and
no `MULTI`/`EXEC` transactions.

## License

MIT — see [LICENSE](LICENSE).
