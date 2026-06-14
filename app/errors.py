"""Contract-shaped errors: {"error": {"code", "message", "fields"?}}."""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ContractError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, fields: dict | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.fields = fields


# Convenience constructors mirroring API_CONTRACT.md error codes.
def invalid_credentials():
    return ContractError("invalid_credentials", "Invalid credentials.", 401)


def not_verified():
    return ContractError("not_verified", "Account not fully verified.", 403)


def code_invalid():
    return ContractError("code_invalid", "That code is not correct.", 400)


def code_expired():
    return ContractError("code_expired", "That code has expired.", 400)


def code_max_attempts():
    return ContractError("code_max_attempts", "Too many attempts; request a new code.", 429)


def already_exists(message="That account already exists."):
    return ContractError("already_exists", message, 409)


def not_found(message="Not found."):
    return ContractError("not_found", message, 404)


def forbidden(message="You do not have permission."):
    return ContractError("forbidden", message, 403)


def validation_error(fields: dict, message="Validation failed."):
    return ContractError("validation_error", message, 422, fields=fields)


def _envelope(code, message, fields=None):
    body = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return body


def register_handlers(app):
    @app.exception_handler(ContractError)
    async def _contract(request: Request, exc: ContractError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.fields),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = {}
        for e in exc.errors():
            loc = [p for p in e["loc"] if p not in ("body", "query", "path")]
            key = loc[-1] if loc else "non_field"
            fields[str(key)] = e["msg"]
        return JSONResponse(status_code=422, content=_envelope("validation_error",
                                                               "Validation failed.", fields))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found"}.get(
            exc.status_code, "error"
        )
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, message))
