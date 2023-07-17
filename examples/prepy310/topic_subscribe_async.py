import asyncio
import logging
from datetime import timedelta

from example_utils.example_logging import initialize_logging

from momento import (
    CacheClient,
    Configurations,
    CredentialProvider,
    TopicClientAsync,
    TopicConfigurations,
)
from momento.errors import SdkException
from momento.responses import CreateCache, TopicSubscribe, TopicSubscriptionItem

_AUTH_PROVIDER = CredentialProvider.from_environment_variable("MOMENTO_AUTH_TOKEN")
_CACHE_NAME = "cache"
_NUM_SUBSCRIBERS = 10
_logger = logging.getLogger("topic-subscribe-example")


def setup_cache() -> None:
    with CacheClient(Configurations.Laptop.latest(), _AUTH_PROVIDER, timedelta(seconds=60)) as client:
        response = client.create_cache(_CACHE_NAME)
        if isinstance(response, CreateCache.Error):
            raise response.inner_exception


async def main() -> None:
    initialize_logging()
    setup_cache()
    _logger.info("hello")
    async with TopicClientAsync(
        TopicConfigurations.Default.v1().with_max_subscriptions(_NUM_SUBSCRIBERS), _AUTH_PROVIDER
    ) as client:
        subscriptions = []
        for i in range(0, _NUM_SUBSCRIBERS):
            subscription = await client.subscribe("cache", "my_topic")
            if isinstance(subscription, TopicSubscribe.SubscriptionAsync):
                subscriptions.append(subscription)
            elif isinstance(subscription, TopicSubscribe.Error):
                print("got subscription error: ", subscription.message)

        if len(subscriptions) == 0:
            raise Exception("no subscriptions were successful")

        print(f"{len(subscriptions)} subscriptions polling for items. . .", flush=True)
        tasks = [asyncio.create_task(poll_subscription(subscription)) for subscription in subscriptions]
        try:
            await asyncio.gather(*tasks)
        except SdkException as e:
            print(f"got exception")
            for task in tasks:
                task.cancel()


async def poll_subscription(subscription: TopicSubscribe.SubscriptionAsync):
    async for item in subscription:
        if isinstance(item, TopicSubscriptionItem.Success):
            print(f"got item: {item.value_string} ({item.value_bytes})")
        elif isinstance(item, TopicSubscriptionItem.Error):
            print("stream closed")
            print(item.inner_exception.message)


if __name__ == "__main__":
    asyncio.run(main())
