class DomainError(Exception):
    def __init__(self, code: str, status: int = 409):
        self.code, self.status = code, status

