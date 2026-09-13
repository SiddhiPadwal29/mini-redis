"""
Command implementations. Each handler takes (store, args) where args
excludes the command name itself, and returns a value ready for
resp.encode() (or raises resp.RespError for an error reply).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from .resp import OK, RespError
from .store import Store

Handler = Callable[[Store, List[str]], Any]

COMMANDS: Dict[str, Handler] = {}


def command(name: str):
    def wrapper(fn: Handler) -> Handler:
        COMMANDS[name.upper()] = fn
        return fn

    return wrapper


def _wrong_args(name: str) -> RespError:
    return RespError(f"ERR wrong number of arguments for '{name.lower()}' command")


def _expect_type(store: Store, key: str, expected: type, name: str):
    value = store.get_raw(key)
    if value is None:
        return None
    if not isinstance(value, expected):
        raise RespError(
            "WRONGTYPE Operation against a key holding the wrong kind of value"
        )
    return value


# -- connection ---------------------------------------------------------

@command("PING")
def cmd_ping(store: Store, args: List[str]):
    return args[0] if args else OK


@command("ECHO")
def cmd_echo(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("ECHO")
    return args[0]


# -- strings --------------------------------------------------------------

@command("SET")
def cmd_set(store: Store, args: List[str]):
    if len(args) < 2:
        raise _wrong_args("SET")
    key, value, *opts = args
    ex_seconds = None
    i = 0
    while i < len(opts):
        opt = opts[i].upper()
        if opt == "EX" and i + 1 < len(opts):
            ex_seconds = float(opts[i + 1])
            i += 2
        elif opt == "PX" and i + 1 < len(opts):
            ex_seconds = float(opts[i + 1]) / 1000.0
            i += 2
        else:
            raise RespError("ERR syntax error")
    store.set_raw(key, value, ex=ex_seconds)
    return OK


@command("GET")
def cmd_get(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("GET")
    value = _expect_type(store, args[0], str, "GET")
    return value


@command("APPEND")
def cmd_append(store: Store, args: List[str]):
    if len(args) != 2:
        raise _wrong_args("APPEND")
    key, suffix = args
    current = _expect_type(store, key, str, "APPEND") or ""
    new_value = current + suffix
    store.set_raw(key, new_value)
    return len(new_value)


@command("INCR")
def cmd_incr(store: Store, args: List[str]):
    return _incr_by(store, args, 1, "INCR")


@command("DECR")
def cmd_decr(store: Store, args: List[str]):
    return _incr_by(store, args, -1, "DECR")


@command("INCRBY")
def cmd_incrby(store: Store, args: List[str]):
    if len(args) != 2:
        raise _wrong_args("INCRBY")
    return _incr_by(store, args[:1], int(args[1]), "INCRBY")


def _incr_by(store: Store, args: List[str], delta: int, name: str):
    if len(args) != 1:
        raise _wrong_args(name)
    key = args[0]
    current = _expect_type(store, key, str, name)
    try:
        n = int(current) if current is not None else 0
    except ValueError:
        raise RespError("ERR value is not an integer or out of range")
    n += delta
    store.set_raw(key, str(n))
    return n


# -- generic keyspace -----------------------------------------------------

@command("DEL")
def cmd_del(store: Store, args: List[str]):
    if not args:
        raise _wrong_args("DEL")
    return store.delete(*args)


@command("EXISTS")
def cmd_exists(store: Store, args: List[str]):
    if not args:
        raise _wrong_args("EXISTS")
    return store.exists(*args)


@command("EXPIRE")
def cmd_expire(store: Store, args: List[str]):
    if len(args) != 2:
        raise _wrong_args("EXPIRE")
    ok = store.expire(args[0], float(args[1]))
    return 1 if ok else 0


@command("TTL")
def cmd_ttl(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("TTL")
    return store.ttl(args[0])


@command("PERSIST")
def cmd_persist(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("PERSIST")
    return 1 if store.persist(args[0]) else 0


@command("TYPE")
def cmd_type(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("TYPE")
    from .resp import SimpleString

    return SimpleString(store.type_of(args[0]))


@command("KEYS")
def cmd_keys(store: Store, args: List[str]):
    pattern = args[0] if args else "*"
    return store.keys(pattern)


@command("DBSIZE")
def cmd_dbsize(store: Store, args: List[str]):
    return store.dbsize()


@command("FLUSHALL")
def cmd_flushall(store: Store, args: List[str]):
    store.flush_all()
    return OK


@command("SAVE")
def cmd_save(store: Store, args: List[str]):
    store.save()
    return OK


# -- lists ------------------------------------------------------------------

def _get_list(store: Store, key: str, name: str) -> list:
    value = _expect_type(store, key, list, name)
    return value if value is not None else []


@command("LPUSH")
def cmd_lpush(store: Store, args: List[str]):
    if len(args) < 2:
        raise _wrong_args("LPUSH")
    key, *values = args
    lst = _get_list(store, key, "LPUSH")
    for v in values:
        lst.insert(0, v)
    store.set_raw(key, lst)
    return len(lst)


@command("RPUSH")
def cmd_rpush(store: Store, args: List[str]):
    if len(args) < 2:
        raise _wrong_args("RPUSH")
    key, *values = args
    lst = _get_list(store, key, "RPUSH")
    lst.extend(values)
    store.set_raw(key, lst)
    return len(lst)


@command("LPOP")
def cmd_lpop(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("LPOP")
    lst = _get_list(store, args[0], "LPOP")
    if not lst:
        return None
    value = lst.pop(0)
    store.set_raw(args[0], lst)
    return value


@command("RPOP")
def cmd_rpop(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("RPOP")
    lst = _get_list(store, args[0], "RPOP")
    if not lst:
        return None
    value = lst.pop()
    store.set_raw(args[0], lst)
    return value


@command("LLEN")
def cmd_llen(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("LLEN")
    return len(_get_list(store, args[0], "LLEN"))


@command("LRANGE")
def cmd_lrange(store: Store, args: List[str]):
    if len(args) != 3:
        raise _wrong_args("LRANGE")
    key, start, stop = args[0], int(args[1]), int(args[2])
    lst = _get_list(store, key, "LRANGE")
    n = len(lst)

    def norm(i):
        return max(0, n + i) if i < 0 else i

    start, stop = norm(start), norm(stop)
    return lst[start : stop + 1]


# -- hashes -----------------------------------------------------------------

def _get_hash(store: Store, key: str, name: str) -> dict:
    value = _expect_type(store, key, dict, name)
    return value if value is not None else {}


@command("HSET")
def cmd_hset(store: Store, args: List[str]):
    if len(args) < 3 or len(args) % 2 == 0:
        raise _wrong_args("HSET")
    key, *pairs = args
    h = _get_hash(store, key, "HSET")
    added = 0
    for i in range(0, len(pairs), 2):
        field, value = pairs[i], pairs[i + 1]
        if field not in h:
            added += 1
        h[field] = value
    store.set_raw(key, h)
    return added


@command("HGET")
def cmd_hget(store: Store, args: List[str]):
    if len(args) != 2:
        raise _wrong_args("HGET")
    h = _get_hash(store, args[0], "HGET")
    return h.get(args[1])


@command("HGETALL")
def cmd_hgetall(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("HGETALL")
    h = _get_hash(store, args[0], "HGETALL")
    flat: List[str] = []
    for k, v in h.items():
        flat.extend([k, v])
    return flat


@command("HDEL")
def cmd_hdel(store: Store, args: List[str]):
    if len(args) < 2:
        raise _wrong_args("HDEL")
    key, *fields = args
    h = _get_hash(store, key, "HDEL")
    removed = 0
    for f in fields:
        if f in h:
            del h[f]
            removed += 1
    store.set_raw(key, h)
    return removed


@command("HKEYS")
def cmd_hkeys(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("HKEYS")
    return list(_get_hash(store, args[0], "HKEYS").keys())


@command("HVALS")
def cmd_hvals(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("HVALS")
    return list(_get_hash(store, args[0], "HVALS").values())


# -- sets ---------------------------------------------------------------

def _get_set(store: Store, key: str, name: str) -> set:
    value = _expect_type(store, key, set, name)
    return value if value is not None else set()


@command("SADD")
def cmd_sadd(store: Store, args: List[str]):
    if len(args) < 2:
        raise _wrong_args("SADD")
    key, *members = args
    s = _get_set(store, key, "SADD")
    added = 0
    for m in members:
        if m not in s:
            s.add(m)
            added += 1
    store.set_raw(key, s)
    return added


@command("SREM")
def cmd_srem(store: Store, args: List[str]):
    if len(args) < 2:
        raise _wrong_args("SREM")
    key, *members = args
    s = _get_set(store, key, "SREM")
    removed = 0
    for m in members:
        if m in s:
            s.remove(m)
            removed += 1
    store.set_raw(key, s)
    return removed


@command("SMEMBERS")
def cmd_smembers(store: Store, args: List[str]):
    if len(args) != 1:
        raise _wrong_args("SMEMBERS")
    return list(_get_set(store, args[0], "SMEMBERS"))


@command("SISMEMBER")
def cmd_sismember(store: Store, args: List[str]):
    if len(args) != 2:
        raise _wrong_args("SISMEMBER")
    s = _get_set(store, args[0], "SISMEMBER")
    return 1 if args[1] in s else 0
