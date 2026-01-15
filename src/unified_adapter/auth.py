"""Clerk JWT validation helpers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
import json
from typing import Any, Dict, Optional

import httpx
import jwt


logger = logging.getLogger(__name__)


@dataclass
class AuthContext:
    subject: str
    org_id: Optional[str]
    claims: Dict[str, Any]


class ClerkJwtVerifier:
    def __init__(
        self,
        jwks_url: str,
        issuer: Optional[str],
        audience: Optional[str],
        cache_seconds: int = 3600,
    ) -> None:
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self.cache_seconds = cache_seconds
        self._jwks: Optional[Dict[str, Any]] = None
        self._jwks_fetched_at: float = 0.0

    async def verify(self, token: str) -> AuthContext:
        jwks = await self._get_jwks()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = self._find_key(jwks, kid)
        if not key:
            raise jwt.InvalidKeyError("No matching JWK")

        options = {"verify_aud": self.audience is not None}
        claims = jwt.decode(
            token,
            key=jwt.algorithms.RSAAlgorithm.from_jwk(key),
            algorithms=["RS256"],
            audience=self.audience,
            issuer=self.issuer,
            options=options,
        )

        return AuthContext(
            subject=str(claims.get("sub")),
            org_id=claims.get("org_id") or claims.get("organization_id"),
            claims=claims,
        )

    async def _get_jwks(self) -> Dict[str, Any]:
        if self._jwks and time.time() - self._jwks_fetched_at < self.cache_seconds:
            return self._jwks

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self.jwks_url)
            response.raise_for_status()
            jwks = response.json()

        self._jwks = jwks
        self._jwks_fetched_at = time.time()
        return jwks

    def _find_key(self, jwks: Dict[str, Any], kid: Optional[str]) -> Optional[str]:
        keys = jwks.get("keys", [])
        for key in keys:
            if not kid or key.get("kid") == kid:
                return json.dumps(key)
        return None
