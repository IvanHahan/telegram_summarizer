import json
import os

import redis as sync_redis  # sync Redis client
import redis.asyncio as aioredis


class AsyncRedisStore:
    def __init__(self, redis_url='redis://localhost:6379/0'):
        """
        Initialize the RedisStore with connection parameters.
        :param host: Redis server hostname or IP address.
        :param port: Redis server port.
        :param db: Redis database index.
        """
        self.redis_client = aioredis.Redis.from_url(redis_url, decode_responses=True)

    async def set(self, key, value, expire=1800):
        """
        Set a key-value pair in Redis with an optional expiration time.
        :param key: The key to set.
        :param value: The value to set.
        :param expire: Expiration time in seconds (optional).
        """
        await self.redis_client.set(key, value, ex=expire)

    async def set_object(self, key, value, expire=1800):
        """
        Set a key-value pair in Redis with an optional expiration time.
        :param key: The key to set.
        :param value: The value to set.
        :param expire: Expiration time in seconds (optional).
        """
        await self.redis_client.set(key, json.dumps(value), ex=expire)

    async def get_object(self, key):
        """
        Get the value of a key from Redis and parse it as JSON.
        :param key: The key to retrieve.
        :return: The parsed JSON object associated with the key, or None if the key does not exist.
        """
        value = await self.redis_client.get(key)
        return json.loads(value) if value else None

    async def get(self, key):
        """
        Get the value of a key from Redis.
        :param key: The key to retrieve.
        :return: The value associated with the key, or None if the key does not exist.
        """
        return await self.redis_client.get(key)

    async def delete(self, key):
        """
        Delete a key from Redis.
        :param key: The key to delete.
        """
        await self.redis_client.delete(key)

    def exists(self, key):
        """
        Check if a key exists in Redis.
        :param key: The key to check.
        :return: True if the key exists, False otherwise.
        """
        return self.redis_client.exists(key) > 0

    def increment(self, key, amount=1):
        """
        Increment the value of a key by a specified amount.
        :param key: The key to increment.
        :param amount: The amount to increment by (default is 1).
        :return: The new value of the key after incrementing.
        """
        return self.redis_client.incr(key, amount)


class RedisStore:
    def __init__(self, redis_url='redis://localhost:6379/0'):
        """
        Initialize the synchronous RedisStore with connection parameters.
        :param host: Redis server hostname or IP address.
        :param port: Redis server port.
        :param db: Redis database index.
        """
        self.redis_client = sync_redis.Redis.from_url(redis_url, decode_responses=True)

    def set(self, key, value, expire=1800):
        """
        Set a key-value pair in Redis with an optional expiration time.
        :param key: The key to set.
        :param value: The value to set.
        :param expire: Expiration time in seconds (optional).
        """
        self.redis_client.set(key, value, ex=expire)

    def set_object(self, key, value, expire=1800):
        """
        Set a JSON-serializable object in Redis.
        """
        self.redis_client.set(key, json.dumps(value), ex=expire)

    def get(self, key):
        """
        Get the value of a key from Redis.
        """
        return self.redis_client.get(key)

    def get_object(self, key):
        """
        Get a JSON-parsed object from Redis.
        """
        value = self.redis_client.get(key)
        return json.loads(value) if value else None

    def delete(self, key):
        """
        Delete a key from Redis.
        """
        self.redis_client.delete(key)

    def exists(self, key):
        """
        Check if a key exists in Redis.
        """
        return self.redis_client.exists(key) > 0

    def increment(self, key, amount=1):
        """
        Increment the value of a key by a specified amount.
        """
        return self.redis_client.incr(key, amount)


class RAMStore:
    def __init__(self):
        """
        Initialize the RAMStore with an in-memory dictionary.
        """
        self.store = {}

    def set(self, key, value, expire=None):
        """
        Set a key-value pair in the in-memory store.
        :param key: The key to set.
        :param value: The value to set.
        :param expire: Expiration time in seconds (optional, not implemented for RAMStore).
        """
        self.store[key] = value

    def get(self, key):
        """
        Get the value of a key from the in-memory store.
        :param key: The key to retrieve.
        :return: The value associated with the key, or None if the key does not exist.
        """
        return self.store.get(key)

    def delete(self, key):
        """
        Delete a key from the in-memory store.
        :param key: The key to delete.
        """
        if key in self.store:
            del self.store[key]

    def exists(self, key):
        """
        Check if a key exists in the in-memory store.
        :param key: The key to check.
        :return: True if the key exists, False otherwise.
        """
        return key in self.store

    def increment(self, key, amount=1):
        """
        Increment the value of a key by a specified amount in the in-memory store.
        :param key: The key to increment.
        :param amount: The amount to increment by (default is 1).
        :return: The new value of the key after incrementing.
        """
        if key in self.store and isinstance(self.store[key], (int, float)):
            self.store[key] += amount
        else:
            self.store[key] = amount
        return self.store[key]


def create_store(store_type='ram', **kwargs):
    """
    Factory function to create a store instance.
    :param store_type: The type of store to create ('ram', 'redis', or 'async_redis').
    :param kwargs: Additional arguments for the store initialization.
    :return: An instance of RAMStore, RedisStore, or AsyncRedisStore.
    :raises ValueError: If an unsupported store_type is provided.
    """
    if store_type == 'ram':
        return RAMStore()
    elif store_type == 'redis':
        return RedisStore(**kwargs)
    elif store_type == 'async_redis':
        return AsyncRedisStore(**kwargs)
    else:
        raise ValueError(f"Unsupported store_type: {store_type}")
    

_store_instance = None

def get_store():
    global _store_instance
    if _store_instance is None:
        _store_instance = create_store(store_type=os.environ.get('STORE_TYPE', 'redis'), 
                                       redis_url=os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
    return _store_instance

store = get_store()