class IdolmasterException(Exception):

    def __init__(self, message="Internal Server Error"):
        self.message = message


class IdolmasterRequestTimeout(IdolmasterException):
    def __init__(self, message="Request timeout"):
        super().__init__(message)
