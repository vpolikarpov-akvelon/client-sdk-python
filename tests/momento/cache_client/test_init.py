import os
from datetime import timedelta

import pytest

from momento import CacheClient
from momento.auth import CredentialProvider
from momento.config import Configuration
from momento.errors import InvalidArgumentException


def test_init_throws_exception_when_client_uses_negative_default_ttl(
    configuration: Configuration, credential_provider: CredentialProvider
) -> None:
    with pytest.raises(InvalidArgumentException, match="TTL must be a positive amount of time."):
        CacheClient(configuration, credential_provider, timedelta(seconds=-1))


def test_init_throws_exception_for_non_jwt_token(configuration: Configuration, default_ttl_seconds: timedelta) -> None:
    with pytest.raises(InvalidArgumentException, match="Invalid Auth token."):
        os.environ["BAD_AUTH_TOKEN"] = "notanauthtoken"
        credential_provider = CredentialProvider.from_environment_variable("BAD_AUTH_TOKEN")
        CacheClient(configuration, credential_provider, default_ttl_seconds)


def test_init_throws_exception_when_client_uses_integer_request_timeout_ms(
    configuration: Configuration, credential_provider: CredentialProvider, default_ttl_seconds: int
) -> None:
    with pytest.raises(InvalidArgumentException, match="Request timeout must be a timedelta."):
        configuration.with_client_timeout(-1)  # type: ignore[arg-type]


def test_init_throws_exception_when_client_uses_negative_request_timeout_ms(
    configuration: Configuration, credential_provider: CredentialProvider, default_ttl_seconds: timedelta
) -> None:
    with pytest.raises(InvalidArgumentException, match="Request timeout must be a positive amount of time."):
        configuration = configuration.with_client_timeout(timedelta(seconds=-1))
        CacheClient(configuration, credential_provider, default_ttl_seconds)


def test_init_throws_exception_when_client_uses_zero_request_timeout_ms(
    configuration: Configuration, credential_provider: CredentialProvider, default_ttl_seconds: timedelta
) -> None:
    with pytest.raises(InvalidArgumentException, match="Request timeout must be a positive amount of time."):
        configuration = configuration.with_client_timeout(timedelta(seconds=0))
        CacheClient(configuration, credential_provider, default_ttl_seconds)
