from fastapi import HTTPException, status


class TalentLibraryException(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


class NotFoundError(TalentLibraryException):
    def __init__(self, resource: str, id: str | int):
        super().__init__(
            detail=f"{resource} with id {id} not found",
            status_code=status.HTTP_404_NOT_FOUND
        )


class ValidationError(TalentLibraryException):
    def __init__(self, detail: str):
        super().__init__(detail=detail, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


class AIServiceError(TalentLibraryException):
    def __init__(self, detail: str = "AI service temporarily unavailable"):
        super().__init__(detail=detail, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
