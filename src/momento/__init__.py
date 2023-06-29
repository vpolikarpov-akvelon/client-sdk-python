"""Momento client library.

Instantiate a client with `CacheClient` or `CacheClientAsync` (for asyncio).
Use `CredentialProvider` to read credentials for the client.
Use `Configurations` for pre-built network configurations.
"""

import logging

from momento import logs

from .auth import CredentialProvider
from .cache_client import CacheClient
from .cache_client_async import CacheClientAsync
from .topic_client_async import TopicClientAsync
from .config import Configurations
from .config import TopicConfigurations

logging.getLogger("momentosdk").addHandler(logging.NullHandler())
logs.initialize_momento_logging()

__all__ = [
    "CredentialProvider",
    "Configurations",
    "TopicConfigurations",
    "CacheClient",
    "CacheClientAsync",
    "TopicClientAsync",
]
