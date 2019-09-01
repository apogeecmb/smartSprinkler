
class BasicException(Exception):
    def __init__(self, message):
        self.message = message

class ModuleException(Exception):
    def __init__(self, message, exception=[], tb=[]):
        self.message = message
        self.exception = exception
        self.traceback = tb


