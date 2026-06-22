import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import jwt
import requests
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import SUPABASE_JWKS_URL, SUPABASE_JWT_AUDIENCE, SUPABASE_URL


@dataclass
class AuthenticatedUser:
    user_id: str
    email: Optional[str]
    claims: Dict[str, Any]


class SupabaseJWTVerifier:
    def __init__(self, jwks_ttl_seconds: int = 900):
        self.jwks_ttl_seconds = jwks_ttl_seconds
        self._jwks: Optional[Dict[str, Any]] = None
        self._jwks_loaded_at: float = 0
        self._security = HTTPBearer(auto_error=False)
        self._issuer = f"{SUPABASE_URL.rstrip('/')}/auth/v1" if SUPABASE_URL else None

    def _resolve_jwks_url(self) -> str:
        if SUPABASE_JWKS_URL:
            return SUPABASE_JWKS_URL
        if not SUPABASE_URL:
            raise HTTPException(status_code=500, detail="SUPABASE_URL or SUPABASE_JWKS_URL is required")
        return f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"

    def _load_jwks(self) -> Dict[str, Any]:
        is_expired = (time.time() - self._jwks_loaded_at) >= self.jwks_ttl_seconds
        if self._jwks and not is_expired:
            return self._jwks

        try:
            response = requests.get(self._resolve_jwks_url(), timeout=5)
            response.raise_for_status()
            self._jwks = response.json()
        except requests.RequestException as exc:
            raise HTTPException(status_code=503, detail="Unable to load Supabase JWKS") from exc
        self._jwks_loaded_at = time.time()
        return self._jwks

    def verify(self, token: str) -> AuthenticatedUser:
        from src import config as _cfg
        if _cfg.SUPABASE_JWT_SECRET:
            try:
                payload = jwt.decode(
                    token, _cfg.SUPABASE_JWT_SECRET, algorithms=["HS256"],
                    options={"verify_aud": False},
                )
            except jwt.PyJWTError as exc:
                raise HTTPException(status_code=401, detail="Invalid or expired auth token") from exc
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid auth token payload")
            return AuthenticatedUser(user_id=user_id, email=payload.get("email"), claims=payload)

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid auth token header") from exc

        kid = header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Missing key id in auth token")

        keys = self._load_jwks().get("keys", [])
        key = next((k for k in keys if k.get("kid") == kid), None)
        if not key:
            self._jwks_loaded_at = 0
            keys = self._load_jwks().get("keys", [])
            key = next((k for k in keys if k.get("kid") == kid), None)
            if not key:
                raise HTTPException(status_code=401, detail="Unknown signing key")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
        decode_kwargs: Dict[str, Any] = {
            "algorithms": ["RS256"],
            "options": {"verify_signature": True, "verify_aud": bool(SUPABASE_JWT_AUDIENCE)},
        }
        if SUPABASE_JWT_AUDIENCE:
            decode_kwargs["audience"] = SUPABASE_JWT_AUDIENCE
        if self._issuer:
            decode_kwargs["issuer"] = self._issuer

        try:
            payload = jwt.decode(token, public_key, **decode_kwargs)
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid or expired auth token") from exc

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid auth token payload")

        return AuthenticatedUser(
            user_id=user_id,
            email=payload.get("email"),
            claims=payload,
        )

    def dependency(self):
        def _get_current_user(
            credentials: HTTPAuthorizationCredentials = Depends(self._security),
        ) -> AuthenticatedUser:
            if not credentials or credentials.scheme.lower() != "bearer":
                raise HTTPException(status_code=401, detail="Missing bearer token")
            return self.verify(credentials.credentials)

        return _get_current_user


jwt_verifier = SupabaseJWTVerifier()
get_current_user = jwt_verifier.dependency()
