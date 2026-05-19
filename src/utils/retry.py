import time
import functools
from typing import TypeVar, Callable, Any
from src.utils.logger import log

T = TypeVar("T")


def retry(max_retries: int = 3, base_delay: float = 1.0, exceptions: tuple = (Exception,)):
    """
    Decorator that retries a function with exponential backoff on failure.

    Usage:
        @retry(max_retries=3, base_delay=1.0)
        def call_api():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error: Exception | None = None

            for attempt in range(1, max_retries + 2):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e

                    if attempt > max_retries:
                        log.error(f"All {max_retries} retry attempts exhausted for '{func.__name__}'")
                        break

                    delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff
                    log.warning(
                        f"Attempt {attempt}/{max_retries} failed for '{func.__name__}'. "
                        f"Retrying in {delay:.1f}s... Error: {e}"
                    )
                    time.sleep(delay)

            raise last_error  # type: ignore

        return wrapper
    return decorator


def sleep(seconds: float) -> None:
    """Sleep for given seconds (with log output)."""
    log.debug(f"Sleeping for {seconds}s...")
    time.sleep(seconds)
