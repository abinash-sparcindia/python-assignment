"""Consistent, safe API errors for client-visible failures."""

from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass
class ApiError(Exception):
    status_code: int
    field: str
    message: str


def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"errors": [{"field": exc.field, "message": exc.message}]},
    )
