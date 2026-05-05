import redis
import json

r = redis.Redis(host="localhost", port=6379, decode_responses=True)


def get_cache(key):
    value = r.get(key)
    return json.loads(value) if value else None


def set_cache(key, value, ttl=3600):
    r.setex(key, ttl, json.dumps(value))