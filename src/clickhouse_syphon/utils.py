import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from loguru import logger


def log_execution_time(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to log the execution time of a function.

    Parameters:
        func: The function to be decorated.

    Returns:
        The wrapped function that logs execution time.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        duration = time.perf_counter() - start_time
        logger.info(f"'{func.__name__}' executed in {duration:.4f} seconds")
        return result

    return wrapper
