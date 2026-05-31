from typing import Any, Dict, Optional

import httpx


class AsyncDBApiConnector:
    def __init__(self, host: str = "http://localhost:8000", timeout: int = 10) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _url(self, endpoint: str) -> str:
        return f"{self.host}/{endpoint.lstrip('/')}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        client = await self._get_client()
        response = await client.get(self._url(endpoint), params=params)
        response.raise_for_status()
        return response.json() if response.text else None

    async def post(
        self,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        client = await self._get_client()
        response = await client.post(self._url(endpoint), json=payload, params=params)
        response.raise_for_status()
        return response.json() if response.text else None
