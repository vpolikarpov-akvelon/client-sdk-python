import time
from datetime import timedelta
from functools import partial
from typing import Optional

from pytest import fixture
from pytest_describe import behaves_like
from typing_extensions import Protocol

from momento import CacheClient
from momento.errors import MomentoErrorCode
from momento.responses import CacheDelete, CacheGet, CacheSet, CacheSetIfNotExists
from momento.responses.mixins import ErrorResponseMixin
from momento.responses.response import CacheResponse
from momento.typing import TCacheName, TScalarKey, TScalarValue
from tests.utils import str_to_bytes, uuid_bytes, uuid_str

from .shared_behaviors import (
    TCacheNameValidator,
    TConnectionValidator,
    TKeyValidator,
    a_cache_name_validator,
    a_connection_validator,
    a_key_validator,
)


class TTtlSetter(Protocol):
    def __call__(self, cache_name: TCacheName, key: TScalarKey, ttl: Optional[timedelta] = None) -> CacheResponse:
        ...


def a_ttl_setter() -> None:
    def expires_items_after_ttl(ttl_setter: TTtlSetter, client: CacheClient, cache_name: TCacheName) -> None:
        key = uuid_str()

        ttl_setter(cache_name, key, ttl=timedelta(seconds=2))
        get_response = client.get(cache_name, key)
        assert isinstance(get_response, CacheGet.Hit)

        time.sleep(4)
        get_response = client.get(cache_name, key)
        assert isinstance(get_response, CacheGet.Miss)

    def with_different_ttl(ttl_setter: TTtlSetter, client: CacheClient, cache_name: TCacheName) -> None:
        key1 = uuid_str()
        key2 = uuid_str()

        ttl_setter(cache_name, key1, ttl=timedelta(seconds=2))
        ttl_setter(cache_name, key2)

        # Before
        get_response = client.get(cache_name, key1)
        assert isinstance(get_response, CacheGet.Hit)
        get_response = client.get(cache_name, key2)
        assert isinstance(get_response, CacheGet.Hit)

        time.sleep(4)

        # After
        get_response = client.get(cache_name, key1)
        assert isinstance(get_response, CacheGet.Miss)
        get_response = client.get(cache_name, key2)
        assert isinstance(get_response, CacheGet.Hit)

    def negative_ttl_throws_exception(ttl_setter: TTtlSetter, client: CacheClient, cache_name: str) -> None:
        set_response = ttl_setter(cache_name, "foo", ttl=timedelta(seconds=-1))
        if isinstance(set_response, ErrorResponseMixin):
            assert set_response.error_code == MomentoErrorCode.INVALID_ARGUMENT_ERROR
            assert set_response.inner_exception.message == "TTL must be a positive amount of time."
        else:
            assert False


class TSetter(Protocol):
    def __call__(
        self, cache_name: TCacheName, key: TScalarKey, value: TScalarValue, ttl: Optional[timedelta] = None
    ) -> CacheResponse:
        ...


def a_setter() -> None:
    def with_null_value_throws_exception(setter: TSetter, client: CacheClient, cache_name: str) -> None:
        set_response = setter(cache_name, "foo", None)  # type:ignore[arg-type]
        if isinstance(set_response, ErrorResponseMixin):
            assert set_response.error_code == MomentoErrorCode.INVALID_ARGUMENT_ERROR
        else:
            assert False

    def with_bad_value_throws_exception(setter: TSetter, client: CacheClient, cache_name: str) -> None:
        set_response = setter(cache_name, "foo", 1)  # type:ignore[arg-type]
        if isinstance(set_response, ErrorResponseMixin):
            assert set_response.error_code == MomentoErrorCode.INVALID_ARGUMENT_ERROR
            assert set_response.inner_exception.message == "Unsupported type for value: <class 'int'>"
        else:
            assert False


def describe_set_and_get() -> None:
    def with_hit(client: CacheClient, cache_name: str) -> None:
        key = uuid_str()
        value = uuid_str()

        set_resp = client.set(cache_name, key, value)
        assert isinstance(set_resp, CacheSet.Success)

        get_resp = client.get(cache_name, key)
        if isinstance(get_resp, CacheGet.Hit):
            assert get_resp.value_string == value
            assert get_resp.value_bytes == str_to_bytes(value)
        else:
            assert False

    def with_byte_key_values(client: CacheClient, cache_name: str) -> None:
        key = uuid_bytes()
        value = uuid_bytes()

        set_resp = client.set(cache_name, key, value)
        assert isinstance(set_resp, CacheSet.Success)

        get_resp = client.get(cache_name, key)
        assert isinstance(get_resp, CacheGet.Hit)
        assert get_resp.value_bytes == value


@behaves_like(a_cache_name_validator, a_key_validator, a_connection_validator)
def describe_get() -> None:
    @fixture
    def cache_name_validator(client: CacheClient) -> TCacheNameValidator:
        key = uuid_str()
        return partial(client.get, key=key)

    @fixture
    def key_validator(client: CacheClient, cache_name: TCacheName) -> TKeyValidator:
        return partial(client.get, cache_name=cache_name)

    @fixture
    def connection_validator(cache_name: TCacheName, key: TScalarKey) -> TConnectionValidator:
        def _connection_validator(client: CacheClient) -> CacheResponse:
            return client.get(cache_name, key)

        return _connection_validator

    def returns_miss(client: CacheClient, cache_name: str) -> None:
        key = uuid_str()

        get_resp = client.get(cache_name, key)
        assert isinstance(get_resp, CacheGet.Miss)


@behaves_like(a_cache_name_validator)
@behaves_like(a_key_validator)
@behaves_like(a_connection_validator)
@behaves_like(a_ttl_setter)
def describe_increment() -> None:
    @fixture
    def cache_name_validator(client: CacheClient) -> TCacheNameValidator:
        key = uuid_str()
        return partial(client.increment, key=key)

    @fixture
    def key_validator(client: CacheClient, cache_name: TCacheName) -> TKeyValidator:
        return partial(client.increment, cache_name=cache_name)

    @fixture
    def connection_validator(cache_name: TCacheName, key: TScalarKey) -> TConnectionValidator:
        def _connection_validator(client: CacheClient) -> CacheResponse:
            return client.increment(cache_name, key)

        return _connection_validator

    @fixture
    def ttl_setter(client: CacheClient) -> TTtlSetter:
        return partial(client.increment, amount=5)

    def it_expires_items_after_ttl(client: CacheClient, cache_name: TCacheName) -> None:
        key = uuid_str()

        client.increment(cache_name, key, ttl=timedelta(seconds=2))
        get_response = client.get(cache_name, key)
        assert isinstance(get_response, CacheGet.Hit)

        time.sleep(4)
        get_response = client.get(cache_name, key)
        assert isinstance(get_response, CacheGet.Miss)


@behaves_like(a_cache_name_validator)
@behaves_like(a_key_validator)
@behaves_like(a_connection_validator)
@behaves_like(a_ttl_setter)
@behaves_like(a_setter)
def describe_set() -> None:
    @fixture
    def cache_name_validator(client: CacheClient) -> TCacheNameValidator:
        key = uuid_str()
        value = uuid_str()
        return partial(client.set, key=key, value=value)

    @fixture
    def key_validator(client: CacheClient, cache_name: TCacheName) -> TKeyValidator:
        value = uuid_str()
        return partial(client.set, cache_name=cache_name, value=value)

    @fixture
    def connection_validator(cache_name: TCacheName, key: TScalarKey, value: TScalarValue) -> TConnectionValidator:
        def _connection_validator(client: CacheClient) -> CacheResponse:
            return client.set(cache_name, key, value)

        return _connection_validator

    @fixture
    def setter(client: CacheClient) -> TSetter:
        return partial(client.set)

    @fixture
    def ttl_setter(client: CacheClient) -> TTtlSetter:
        return partial(client.set, value=uuid_str())


@behaves_like(a_cache_name_validator)
@behaves_like(a_key_validator)
@behaves_like(a_connection_validator)
@behaves_like(a_ttl_setter)
@behaves_like(a_setter)
def describe_set_if_not_exists() -> None:
    @fixture
    def cache_name_validator(client: CacheClient) -> TCacheNameValidator:
        key = uuid_str()
        value = uuid_str()
        return partial(client.set_if_not_exists, key=key, value=value)

    @fixture
    def key_validator(client: CacheClient, cache_name: TCacheName) -> TKeyValidator:
        value = uuid_str()
        return partial(client.set_if_not_exists, cache_name=cache_name, value=value)

    @fixture
    def connection_validator(cache_name: TCacheName, key: TScalarKey, value: TScalarValue) -> TConnectionValidator:
        def _connection_validator(client: CacheClient) -> CacheResponse:
            return client.set_if_not_exists(cache_name, key, value)

        return _connection_validator

    @fixture
    def setter(client: CacheClient) -> TSetter:
        return partial(client.set_if_not_exists)

    @fixture
    def ttl_setter(client: CacheClient) -> TTtlSetter:
        return partial(client.set_if_not_exists, value=uuid_str())

    def it_only_sets_when_the_key_does_not_exist(
        client: CacheClient,
        cache_name: TCacheName,
    ) -> None:
        key = uuid_str()
        value = uuid_str()

        get_resp = client.get(cache_name, key)
        assert isinstance(get_resp, CacheGet.Miss)

        set_resp = client.set_if_not_exists(cache_name, key, value)
        assert isinstance(set_resp, CacheSetIfNotExists.Stored)

        get_resp = client.get(cache_name, key)
        assert isinstance(get_resp, CacheGet.Hit)
        assert get_resp.value_string == str(value)

        set_resp = client.set_if_not_exists(cache_name, key, uuid_str())
        assert isinstance(set_resp, CacheSetIfNotExists.NotStored)

        get_resp = client.get(cache_name, key)
        assert isinstance(get_resp, CacheGet.Hit)
        assert get_resp.value_string == str(value)


@behaves_like(a_cache_name_validator)
@behaves_like(a_key_validator)
@behaves_like(a_connection_validator)
def describe_delete() -> None:
    @fixture
    def cache_name_validator(client: CacheClient) -> TCacheNameValidator:
        key = uuid_str()
        return partial(client.delete, key=key)

    @fixture
    def key_validator(client: CacheClient, cache_name: TCacheName) -> TKeyValidator:
        return partial(client.delete, cache_name=cache_name)

    @fixture
    def connection_validator(cache_name: TCacheName, key: TScalarKey) -> TConnectionValidator:
        def _connection_validator(client: CacheClient) -> CacheResponse:
            return client.delete(cache_name, key)

        return _connection_validator

    def key_doesnt_exist(client: CacheClient, cache_name: str) -> None:
        key = uuid_str()
        get_response = client.get(cache_name, key)
        assert isinstance(get_response, CacheGet.Miss)

        delete_response = client.delete(cache_name, key)
        assert isinstance(delete_response, CacheDelete.Success)
        get_response = client.get(cache_name, key)
        assert isinstance(get_response, CacheGet.Miss)

    def delete_a_key(client: CacheClient, cache_name: str) -> None:
        # Set an item to then delete...
        key, value = uuid_str(), uuid_str()
        get_response = client.get(cache_name, key)
        assert isinstance(get_response, CacheGet.Miss)
        set_response = client.set(cache_name, key, value)
        assert isinstance(set_response, CacheSet.Success)

        get_response = client.get(cache_name, key)
        assert isinstance(get_response, CacheGet.Hit)

        # Delete
        delete_response = client.delete(cache_name, key)
        assert isinstance(delete_response, CacheDelete.Success)

        # Verify deleted
        get_response = client.get(cache_name, key)
        assert isinstance(get_response, CacheGet.Miss)
