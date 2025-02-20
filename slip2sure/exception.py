class Slip2SureError(Exception):
    def __init__(self, result: str, message: str):
        super().__init__(f"[{result}] {message}")
        self.errorCode = result
        self.errorMessage = message