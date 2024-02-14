import os

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader, APIKeyQuery, HTTPBearer

query_scheme = APIKeyQuery(name="api_key", auto_error=False)
header_scheme = APIKeyHeader(name="x_api_key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def verify_apikey(
    apikey_query: str = Depends(query_scheme),
    apikey_header: str = Depends(header_scheme),
    apikey_bearer: str = Depends(bearer_scheme),
) -> None:
    apikey = apikey_query or apikey_header or apikey_bearer
    if not apikey == os.environ["API_KEY"]:
        raise HTTPException(status_code=401, detail="Unauthorized")
