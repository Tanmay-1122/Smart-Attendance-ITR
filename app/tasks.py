import functools
import traceback
from concurrent.futures import ThreadPoolExecutor
from flask import current_app

_executor = ThreadPoolExecutor(max_workers=4)


def run_async(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        app = current_app._get_current_object()
        def _run():
            with app.app_context():
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    app.logger.error(f"[ASYNC] {func.__name__} failed: {e}\n{traceback.format_exc()}")
        return _executor.submit(_run)
    return wrapper
