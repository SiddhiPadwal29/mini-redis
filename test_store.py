import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from miniredis.commands import COMMANDS
from miniredis.resp import RespError
from miniredis.store import Store


@pytest.fixture
def store():
    return Store(snapshot_path=None)


def run(store, name, *args):
    return COMMANDS[name](store, list(args))


def test_set_get(store):
    run(store, "SET", "foo", "bar")
    assert run(store, "GET", "foo") == "bar"


def test_get_missing_key(store):
    assert run(store, "GET", "nope") is None


def test_del(store):
    run(store, "SET", "a", "1")
    run(store, "SET", "b", "2")
    assert run(store, "DEL", "a", "b", "c") == 2


def test_expire_and_ttl(store):
    run(store, "SET", "temp", "value")
    assert run(store, "TTL", "temp") == -1
    run(store, "EXPIRE", "temp", "10")
    ttl = run(store, "TTL", "temp")
    assert 0 < ttl <= 10


def test_expiry_actually_expires(store):
    store.set_raw("k", "v", ex=0.05)
    assert store.get_raw("k") == "v"
    time.sleep(0.1)
    assert store.get_raw("k") is None


def test_incr_decr(store):
    run(store, "SET", "counter", "10")
    assert run(store, "INCR", "counter") == 11
    assert run(store, "DECR", "counter") == 10
    assert run(store, "INCRBY", "counter", "5") == 15


def test_incr_non_integer_raises(store):
    run(store, "SET", "notnum", "abc")
    with pytest.raises(RespError):
        run(store, "INCR", "notnum")


def test_list_operations(store):
    run(store, "RPUSH", "mylist", "a", "b", "c")
    run(store, "LPUSH", "mylist", "z")
    assert run(store, "LRANGE", "mylist", "0", "-1") == ["z", "a", "b", "c"]
    assert run(store, "LLEN", "mylist") == 4
    assert run(store, "LPOP", "mylist") == "z"
    assert run(store, "RPOP", "mylist") == "c"


def test_hash_operations(store):
    run(store, "HSET", "user:1", "name", "Ada", "role", "engineer")
    assert run(store, "HGET", "user:1", "name") == "Ada"
    flat = run(store, "HGETALL", "user:1")
    assert set(zip(flat[::2], flat[1::2])) == {("name", "Ada"), ("role", "engineer")}
    assert run(store, "HDEL", "user:1", "role") == 1


def test_set_operations(store):
    run(store, "SADD", "tags", "a", "b", "a")
    assert set(run(store, "SMEMBERS", "tags")) == {"a", "b"}
    assert run(store, "SISMEMBER", "tags", "a") == 1
    assert run(store, "SISMEMBER", "tags", "z") == 0
    assert run(store, "SREM", "tags", "a") == 1


def test_wrong_type_error(store):
    run(store, "SET", "str_key", "hello")
    with pytest.raises(RespError):
        run(store, "LPUSH", "str_key", "x")


def test_persistence_round_trip(tmp_path):
    snap = tmp_path / "dump.mrdb"
    s1 = Store(snapshot_path=str(snap))
    run(s1, "SET", "persisted", "yes")
    run(s1, "RPUSH", "mylist", "1", "2")
    s1.save()

    s2 = Store(snapshot_path=str(snap))
    assert run(s2, "GET", "persisted") == "yes"
    assert run(s2, "LRANGE", "mylist", "0", "-1") == ["1", "2"]
