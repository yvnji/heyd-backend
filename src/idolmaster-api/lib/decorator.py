import signal
from functools import wraps

from lib.exception import IdolmasterBadRequestException
from lib.exception import IdolmasterRequestTimeout
from thirdparty.mariadb import get_db_connection


def func_timeout(time_sec):
    def decorator(func):
        def handle_func_timeout(signum, frame):
            raise IdolmasterRequestTimeout("request time out (function : %s, time : %s sec)" % (func.__name__, time_sec))

        @wraps(func)
        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, handle_func_timeout)
            signal.alarm(time_sec)
            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)
            return result
        return wrapper
    return decorator


def mandatory_params(params_keys_list):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            lost_params = []
            for key in params_keys_list:
                if key not in args[2]:
                    lost_params.append(key)
            if lost_params:
                raise IdolmasterBadRequestException(
                    f"Lost parameters : {', '.join(lost_params)}"
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


def preprocessing_cursor(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        db_connection = None
        if not kwargs.get("cursor"):
            db_connection = get_db_connection()
            kwargs["cursor"] = db_connection.cursor()
        if db_connection:
            try:
                res = func(*args, **kwargs)
                kwargs["cursor"].close()
                db_connection.commit()
            except Exception as e:
                db_connection.rollback()
                raise e
            finally:
                db_connection.close()
        else:
            res = func(*args, **kwargs)
        return res
    return wrapper
