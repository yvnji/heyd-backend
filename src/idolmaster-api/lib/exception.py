class IdolmasterException(Exception):
    status_code = 500

    def __init__(self, message="Internal Server Error", result_code=0, headers={}):
        self.result_code = result_code
        self.message = message
        self.headers = headers


class IdolmasterBadRequestException(IdolmasterException):
    status_code = 400

    def __init__(self, message="Bad request", result_code=0, headers={}):
        self.result_code = result_code
        self.message = message
        self.headers = headers


class IdolmasterUnauthorizedException(IdolmasterException):
    status_code = 401

    def __init__(self, message="Unathorized", result_code=0, headers={}):
        self.result_code = result_code
        self.message = message
        self.headers = headers


class IdolmasterForbiddenException(IdolmasterException):
    status_code = 403

    def __init__(self, message="Forbidden", result_code=0, headers={}):
        self.result_code = result_code
        self.message = message
        self.headers = headers


class IdolmasterResourceNotFoundExeption(IdolmasterException):
    status_code = 404

    def __init__(self, message="Resource not found", result_code=0, headers={}):
        self.result_code = result_code
        self.message = message
        self.headers = headers


class IdolmasterRequestTimeout(IdolmasterException):
    status_code = 408

    def __init__(self, message="Request timeout", result_code=0, headers={}):
        self.result_code = result_code
        self.message = message
        self.headers = headers


class IdolmasterConflictResourceException(IdolmasterException):
    status_code = 409

    def __init__(self, message="Conflict resource", result_code=0, headers={}):
        self.result_code = result_code
        self.message = message
        self.headers = headers
