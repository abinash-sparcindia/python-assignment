"""FastAPI application and consistent request validation responses."""

import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from utility_assets.auth import router as auth_router
from utility_assets.errors import ApiError, api_error_handler


def create_app() -> FastAPI:
    app = FastAPI(title="Utility Asset Service", version="0.1.0")
    origins = [origin.strip() for origin in os.environ.get("CORS_ORIGINS", "").split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_exception_handler(ApiError, api_error_handler)

    @app.exception_handler(RequestValidationError)
    def request_validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for issue in exc.errors():
            field = ".".join(str(part) for part in issue["loc"] if part not in {"body", "query", "path"})
            errors.append({"field": field or "request", "message": issue["msg"]})
        return JSONResponse(status_code=422, content={"errors": errors})

    @app.get("/health", tags=["monitoring"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    return app


app = create_app()
