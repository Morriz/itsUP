from fastapi import Depends, HTTPException
from fastapi.security import (
    APIKeyHeader,
    APIKeyQuery,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from lib.data import load_secrets

query_scheme = APIKeyQuery(name="apikey", scheme_name="APIKeyQuery", auto_error=False)
header_scheme = APIKeyHeader(name="X-API-KEY", scheme_name="APIKeyHeader", auto_error=False)
bearer_scheme = HTTPBearer(scheme_name="HTTPBearer", auto_error=False)


def _get_api_key() -> str | None:
    """Resolve the API key from secrets at call time.

    Loaded lazily rather than at import so the module is importable without
    secrets present (tests, CI) and so the lookup can be patched in tests.
    """
    return load_secrets().get("API_KEY")


def verify_apikey(
    apikey_query: str | None = Depends(query_scheme),
    apikey_header: str | None = Depends(header_scheme),
    apikey_bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    api_key = _get_api_key()
    if not api_key:
        raise HTTPException(status_code=503, detail="API_KEY not configured")
    bearer = apikey_bearer.credentials if apikey_bearer else None
    apikey = apikey_query or apikey_header or bearer
    if apikey != api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
