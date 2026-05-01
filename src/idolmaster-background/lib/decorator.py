import threading
from functools import wraps

from lib.exception import IdolmasterRequestTimeout


def func_timeout(time_sec):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = []
            error = []

            def target():
                try:
                    result.append(func(*args, **kwargs))
                except Exception as e:
                    error.append(e)

            thread = threading.Thread(target=target)
            thread.daemon = True  # 메인 스레드가 종료되면 함께 종료되도록 설정
            thread.start()

            thread.join(timeout=time_sec)

            if thread.is_alive():
                # 타임아웃 발생 시 스레드를 강제 종료
                raise IdolmasterRequestTimeout

            if error:
                raise error[0]

            return result[0]

        return wrapper
    return decorator
