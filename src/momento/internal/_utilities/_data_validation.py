from __future__ import annotations

import collections.abc
from datetime import timedelta
from typing import Iterable, Optional, Tuple

from momento.errors import InvalidArgumentException
from momento.typing import (
    TDictionaryFields,
    TDictionaryItems,
    TListValuesInput,
    TSetElementsInput,
    TSetElementsInputBytes,
)

DEFAULT_STRING_CONVERSION_ERROR = "Could not decode bytes to UTF-8"
DEFAULT_LIST_CONVERSION_ERROR = "Could not decode List[bytes] to UTF-8"
DEFAULT_DICTIONARY_CONVERSION_ERROR = "Could not decode Mapping[bytes, bytes] to UTF-8"
DEFAULT_DICTIONARY_FIELDS_CONVERSION_ERROR = "Could not decode Iterable[bytes, bytes] to UTF-8"
DEFAULT_SET_CONVERSION_ERROR = "Could not decode Set[bytes] to UTF-8"


def _validate_name(name: str, field_name: str) -> None:
    if not isinstance(name, str):
        raise InvalidArgumentException(f"{field_name} must be a string")
    if name == "":
        raise InvalidArgumentException(f"{field_name} must not be empty")


def _validate_cache_name(cache_name: str) -> None:
    _validate_name(cache_name, "Cache name")


def _validate_list_name(list_name: str) -> None:
    _validate_name(list_name, "List name")


def _validate_dictionary_name(dictionary_name: str) -> None:
    _validate_name(dictionary_name, "Dictionary name")


def _validate_set_name(set_name: str) -> None:
    _validate_name(set_name, "Set name")


def _as_bytes(
    data: str | bytes,
    error_message: Optional[str] = DEFAULT_STRING_CONVERSION_ERROR,
) -> bytes:
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, bytes):
        return data
    raise InvalidArgumentException(f"{error_message}{type(data)}")


def _gen_iterable_as_bytes(values: Iterable[str | bytes], error_message: str) -> Iterable[bytes]:
    if not isinstance(values, collections.abc.Iterable):
        raise InvalidArgumentException(f"{error_message}{type(values)}")
    for value in values:
        yield _as_bytes(value)


def _gen_list_as_bytes(values: TListValuesInput, error_message: str = DEFAULT_LIST_CONVERSION_ERROR) -> Iterable[bytes]:
    yield from _gen_iterable_as_bytes(values, error_message)


def _gen_dictionary_items_as_bytes(
    items: TDictionaryItems, error_message: str = DEFAULT_DICTIONARY_CONVERSION_ERROR
) -> Iterable[Tuple[bytes, bytes]]:
    if not isinstance(items, collections.abc.Mapping):
        raise InvalidArgumentException(f"{error_message}{type(items)}")
    for key, value in items.items():
        yield (_as_bytes(key), _as_bytes(value))


def _gen_dictionary_fields_as_bytes(
    fields: TDictionaryFields, error_message: str = DEFAULT_DICTIONARY_FIELDS_CONVERSION_ERROR
) -> Iterable[bytes]:
    yield from _gen_iterable_as_bytes(fields, error_message)


def _gen_set_input_as_bytes(
    elements: TSetElementsInput, error_message: str = DEFAULT_SET_CONVERSION_ERROR
) -> TSetElementsInputBytes:
    # NB: the set input does not need to be unique
    yield from _gen_iterable_as_bytes(elements, error_message)


def _validate_timedelta_ttl(ttl: Optional[timedelta], field_name: str) -> None:
    if not isinstance(ttl, timedelta):
        raise InvalidArgumentException(f"{field_name} must be a timedelta.")
    if ttl.total_seconds() <= 0:
        raise InvalidArgumentException(f"{field_name} must be a positive amount of time.")


def _validate_ttl(ttl: Optional[timedelta]) -> None:
    _validate_timedelta_ttl(ttl=ttl, field_name="TTL")


def _validate_request_timeout(request_timeout: Optional[timedelta]) -> None:
    if request_timeout is None:
        return
    _validate_timedelta_ttl(ttl=request_timeout, field_name="Request timeout")
