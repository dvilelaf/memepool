import functools
import time


def rate_limit(interval: int = 5):
    """Rate limit a function call"""

    def decorator(func):
        # Needs to be a mutable to store state
        # We initialize it so we do not wait for some time before the first call
        last_called = [time.time() - interval]

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            elapsed = now - last_called[0]

            if elapsed < interval:
                time.sleep(interval - elapsed)

            last_called[0] = time.time()
            return func(*args, **kwargs)

        return wrapper

    return decorator
