import os

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader, APIKeyQuery, HTTPBearer

query_scheme = APIKeyQuery(name="apikey", scheme_name="APIKeyQuery", auto_error=False)
header_scheme = APIKeyHeader(name="X-API-KEY", scheme_name="APIKeyHeader", auto_error=False)
bearer_scheme = HTTPBearer(scheme_name="HTTPBearer", auto_error=False)


def verify_apikey(
    apikey_query: str = Depends(query_scheme),
    apikey_header: str = Depends(header_scheme),
    apikey_bearer: str = Depends(bearer_scheme),
) -> None:
    apikey = apikey_query or apikey_header or apikey_bearer
    if not apikey == os.environ["API_KEY"]:
        raise HTTPException(status_code=401, detail="Unauthorized")
