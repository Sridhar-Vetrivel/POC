"""Server sign-in (V1-4): check the Entra token on every request, and say who is calling.

``EntraTokenVerifier`` plugs into the MCP SDK's bearer-token support. A token is accepted only if it
is signed by a key from this tenant's published key set, was issued by this tenant (v2.0 format; the
server app's ``requestedAccessTokenVersion`` is 2), is meant for this server app, has not expired and
carries the ``access_as_user`` scope. Anything else gets a 401 before a tool runs.

The token's claims are used for the call log (who) and the token itself is kept only to swap it for a
Graph token (graph.py). It is never logged or returned.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any

import jwt
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from ingenus_mcp.core.config import Settings

log = logging.getLogger("ingenus_mcp.auth")
if not log.handlers:  # stderr only: on stdio, stdout is the protocol channel
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)

_CLAIMS_KEPT = ("iss", "tid", "oid", "preferred_username", "name", "azp", "ver")
_LEEWAY_SECONDS = 60


@dataclass(frozen=True)
class SignedInUser:
    user_id: str  # the stable object id (oid); what the caches are keyed on
    name: str  # what the call log shows (the sign-in name)
    token: str  # the user's access token for this server: used only for the on-behalf-of swap


class EntraTokenVerifier:
    """Implements the SDK's TokenVerifier protocol for tokens issued by one Entra tenant."""

    def __init__(self, settings: Settings, jwks_client: Any | None = None):
        self._settings = settings
        self._jwks = jwks_client or jwt.PyJWKClient(settings.jwks_uri, cache_keys=True)
        self._seen: set[tuple[str, int]] = set()  # (user, token expiry): one login event per token
        self._last_refused: dict[str, float] = {}  # reason -> when it was last logged

    async def verify_token(self, token: str) -> AccessToken | None:
        # The first call fetches the tenant's keys over the network, so keep it off the event loop.
        return await asyncio.to_thread(self.verify, token)

    def verify(self, token: str) -> AccessToken | None:
        s = self._settings
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],  # never 'none' or a shared-secret algorithm
                audience=s.server_client_id,
                issuer=s.issuer,
                options={"require": ["exp", "iss", "aud"]},
                leeway=_LEEWAY_SECONDS,
            )
        except jwt.PyJWTError as exc:
            log.info(
                "token rejected: %s", type(exc).__name__
            )  # the reason class only, never the token
            return self._refused(type(exc).__name__)
        except Exception as exc:  # noqa: BLE001 - e.g. the key set could not be fetched: refuse, say why
            log.warning("token check failed: %s", type(exc).__name__)
            return self._refused(f"keys unavailable ({type(exc).__name__})")

        if claims.get("tid") != s.tenant_id:
            log.info("token rejected: wrong tenant")
            return self._refused("wrong tenant")
        scopes = str(claims.get("scp", "")).split()
        if s.required_scope not in scopes:
            log.info("token rejected: missing scope %s", s.required_scope)
            return self._refused("missing scope")
        access = AccessToken(
            token=token,
            client_id=str(claims.get("azp") or claims.get("appid") or ""),
            scopes=scopes,
            expires_at=int(claims["exp"]),
            resource=str(claims["aud"]),
            subject=str(claims.get("oid") or claims.get("sub") or ""),
            claims={k: claims[k] for k in _CLAIMS_KEPT if k in claims},
        )
        self._accepted(claims)
        return access

    # -- login events (decision 0005): one per accepted token, rate-limited when refused -------
    def _log_login(self, outcome: str, reason: str, claims: dict | None = None) -> None:
        try:
            from ingenus_mcp.core import calllog  # imported here: calllog imports this module

            claims = claims or {}
            event = calllog.make_event(
                "login",
                outcome=outcome,
                reason=reason,
                user=claims.get("preferred_username"),
                user_id=claims.get("oid"),
                client_id=claims.get("azp"),
            )
            calllog.write_record(self._settings.log_path, event, self._settings.audit_store)
        except Exception as exc:  # noqa: BLE001 - a log problem must never refuse a good user
            log.warning("could not write a login event: %s", type(exc).__name__)

    def _accepted(self, claims: dict) -> None:
        key = (str(claims.get("oid") or claims.get("sub") or ""), int(claims["exp"]))
        if key in self._seen:
            return
        if len(self._seen) > 2000:
            self._seen.clear()
        self._seen.add(key)
        self._log_login("accepted", "valid token", claims)

    def _refused(self, reason: str) -> None:
        now = time.monotonic()
        if now - self._last_refused.get(reason, -1e9) >= 10:  # at most one per reason per 10 s
            self._last_refused[reason] = now
            self._log_login("refused", reason)
        return None


def current_token() -> SignedInUser | None:
    """The user behind the request being served, or None if sign-in is off or no token came."""
    access = get_access_token()
    if access is None:
        return None
    claims = access.claims or {}
    user_id = access.subject or str(claims.get("oid") or "")
    if not user_id:
        return None
    name = str(claims.get("preferred_username") or claims.get("name") or user_id)
    return SignedInUser(user_id=user_id, name=name, token=access.token)


def current_user_id() -> str | None:
    """The stable id (oid) of the caller, for the log."""
    user = current_token()
    return user.user_id if user else None


def current_user_name() -> str | None:
    """The sign-in name of the caller, for the call log."""
    user = current_token()
    return user.name if user else None
