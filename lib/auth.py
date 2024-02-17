import os
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import (
    APIKeyHeader,
    APIKeyQuery,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

query_scheme = APIKeyQuery(name="apikey", scheme_name="APIKeyQuery", auto_error=False)
header_scheme = APIKeyHeader(name="X-API-KEY", scheme_name="APIKeyHeader", auto_error=False)
bearer_scheme = HTTPBearer(scheme_name="HTTPBearer", auto_error=False)


def verify_apikey(
    apikey_query: str = Depends(query_scheme),
    apikey_header: str = Depends(header_scheme),
    apikey_bearer: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> None:
    apikey: Any = apikey_query or apikey_header or apikey_bearer.credentials
    if not apikey == os.environ["API_KEY"]:
        raise HTTPException(status_code=401, detail="Unauthorized")
