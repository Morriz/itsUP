from typing import Any

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

# Load API key once at module import time
_secrets = load_secrets()
if "API_KEY" not in _secrets:
    raise ValueError("Missing required secret: API_KEY\nAdd to secrets/itsup.txt or secrets/itsup.enc.txt")
_API_KEY = _secrets["API_KEY"]


def verify_apikey(
    apikey_query: str = Depends(query_scheme),
    apikey_header: str = Depends(header_scheme),
    apikey_bearer: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> None:
    apikey: Any = apikey_query or apikey_header or apikey_bearer.credentials
    if not apikey == _API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
