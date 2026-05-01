class IdolmasterException(Exception):
    def __init__(self, result_code=0, message=""):
        self.result_code = result_code
        self.message = message
