"""Authentication & authorization extension points (the auth seam).

Auth is a cross-cutting framework contract, NOT part of either narrow waist: it runs
*before* a request enters the SSE/orchestrator path, so adding it does not bump
``PROTOCOL_VERSION``. The contracts here are transport-agnostic so one implementation
serves both the web profile (FastAPI, HTTP headers) and the DCC profile (PySide/Maya
host session) -- ``Authenticator`` never sees an HTTP request type.

Users plug in their own mechanism (JWT, OAuth2, API-key, mTLS, studio SSO, ...) by
implementing the two Protocols. The framework ships only:

  * the contracts (``AuthContext`` / ``Principal`` / ``AuthzAction``),
  * the two Protocols (``Authenticator`` / ``Authorizer``),
  * trivial dev/test authorizers (``AllowAllAuthorizer`` / ``DenyAllAuthorizer``),
  * a bridge helper ``session_from_principal`` mapping a verified ``Principal`` onto the
    wire ``SessionContext`` the orchestrator consumes.

Security invariants (§10) are enforced *by the implementations*, not here: adapters
fetch data under the Principal's identity (never a service account), the delegated
``auth_token`` is short-lived / unlogged / uncached, and row-level scoping happens in
``Authorizer`` + adapter RLS.
"""

from __future__ import annotations

from typing import Any
from typing import Protocol
from typing import runtime_checkable

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field as PydanticField
from pydantic import SecretStr

from agentkit_core.models import SessionContext


__all__ = [
    "AllowAllAuthorizer",
    "AuthContext",
    "AuthError",
    "AuthenticationError",
    "Authenticator",
    "AuthorizationError",
    "Authorizer",
    "AuthzAction",
    "DenyAllAuthorizer",
    "Principal",
    "session_from_principal",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AuthError(Exception):
    """Base for authentication/authorization failures. Maps to HTTP 401/403."""


class AuthenticationError(AuthError):
    """Caller identity could not be verified (bad/expired/missing credential). HTTP 401."""


class AuthorizationError(AuthError):
    """Caller is authenticated but lacks permission for the action. HTTP 403."""


# ---------------------------------------------------------------------------
# Inputs / outputs of the auth seam
# ---------------------------------------------------------------------------


class AuthContext(BaseModel):
    """Transport-agnostic bag of raw auth material extracted from the inbound request.

    The app/runtime layer populates this: the web profile fills ``headers``/``query``/
    ``cookies``/``peer`` from the FastAPI ``Request``; a DCC host fills them from the
    studio session. ``Authenticator`` reads whatever it needs (e.g.
    ``context.header("Authorization")``) and never sees an HTTP type, so the same
    implementation works across transports. ``extra="allow"`` lets a runtime stash
    transport-specific extras without a subclass.
    """

    model_config = ConfigDict(extra="allow")

    headers: dict[str, str] = PydanticField(default_factory=dict)
    query: dict[str, str] = PydanticField(default_factory=dict)
    cookies: dict[str, str] = PydanticField(default_factory=dict)
    peer: dict[str, Any] = PydanticField(default_factory=dict)  # remote_addr, tls_sni, ...

    def header(self, name: str) -> str | None:
        """Case-insensitive header lookup (HTTP headers are case-insensitive)."""
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return None


class Principal(BaseModel):
    """The authenticated subject produced by ``Authenticator.authenticate``.

    Carries who the user is (``user_identity``), what they may do
    (``user_permissions``), and a delegated credential for backend data calls
    (``auth_token``, Option B). The app layer bridges it onto a ``SessionContext`` via
    ``session_from_principal``. ``auth_token`` is the delegated BI token (``SecretStr``,
    never serialized) -- adapters fetch data under this identity, never a service account
    (§10). Frozen: a verified identity must not be mutated mid-request.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_identity: str
    user_permissions: tuple[str, ...] = ()  # scopes / RLS roles (immutable)
    auth_token: SecretStr | None = PydanticField(default=None, exclude=True)
    workspace_id: str | None = None
    metadata: dict[str, Any] = PydanticField(default_factory=dict)  # tenant, claims, ...


class AuthzAction(BaseModel):
    """What is being authorized: a verb on an optional target component with its args.

    Passed to ``Authorizer.authorize`` before the verb executes. ``component_id`` is
    ``None`` for non-targeted verbs (``get_catalog``, ``get_semantic_model``). ``args``
    enables field/row-level checks (e.g. "is this filter value allowed for this user?").
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    verb: str
    component_id: str | None = None
    args: dict[str, Any] = PydanticField(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocols (the seam users implement)
# ---------------------------------------------------------------------------


@runtime_checkable
class Authenticator(Protocol):
    """Verifies the caller's identity and produces a ``Principal``.

    Implement JWT / OAuth2 / API-key / mTLS / SSO here. Read credentials from
    ``context`` (``context.header("Authorization")``, cookies, peer cert, ...). Raise
    ``AuthenticationError`` on any failure; the app layer maps it to HTTP 401.

    Async so implementations may do remote work (token introspection, JWKS fetch,
    policy-server call); a purely local impl (signed-JWT verify) simply returns without
    awaiting.
    """

    async def authenticate(self, context: AuthContext) -> Principal:
        """Verify the caller and return their Principal (raise AuthenticationError on failure)."""
        ...


@runtime_checkable
class Authorizer(Protocol):
    """Decides whether a ``Principal`` may perform an ``AuthzAction``.

    Implement RLS / scope / ABAC checks here. Return normally to allow; raise
    ``AuthorizationError`` to deny (the app layer maps it to HTTP 403). Called per verb,
    before execution, with the verb name, target component, and args -- enough for
    field/row-level decisions.
    """

    async def authorize(self, principal: Principal, action: AuthzAction) -> None:
        """Allow (return) or deny (raise AuthorizationError) the action for the principal."""
        ...


# ---------------------------------------------------------------------------
# Trivial authorizers (dev/test only)
# ---------------------------------------------------------------------------


class AllowAllAuthorizer:
    """Trivial ``Authorizer`` that permits every action. For local/dev/mock only."""

    async def authorize(self, principal: Principal, action: AuthzAction) -> None:
        """Always allow."""
        return None


class DenyAllAuthorizer:
    """Trivial ``Authorizer`` that denies every action. For testing denial paths."""

    async def authorize(self, principal: Principal, action: AuthzAction) -> None:
        """Always deny."""
        raise AuthorizationError(
            f"denied: verb={action.verb} component={action.component_id} user={principal.user_identity}"
        )


# ---------------------------------------------------------------------------
# Bridge: Principal -> SessionContext (the wire type the orchestrator sees)
# ---------------------------------------------------------------------------


def session_from_principal(
    principal: Principal,
    *,
    trace_id: str,
    workspace_id: str | None = None,
) -> SessionContext:
    """Build a ``SessionContext`` from an authenticated ``Principal``.

    The app layer calls this after ``Authenticator.authenticate`` succeeds. ``trace_id``
    is always a runtime concern; ``workspace_id`` may come from the Principal (e.g. a JWT
    claim) or be supplied by the runtime (e.g. a path parameter) -- the explicit argument
    wins. The Principal's ``auth_token``, ``user_identity`` and ``user_permissions`` flow
    straight through onto the wire ``SessionContext``.
    """
    resolved_workspace = workspace_id or principal.workspace_id
    if resolved_workspace is None:
        raise ValueError("workspace_id is required: pass it explicitly or set Principal.workspace_id")
    return SessionContext(
        user_identity=principal.user_identity,
        user_permissions=list(principal.user_permissions),
        workspace_id=resolved_workspace,
        trace_id=trace_id,
        auth_token=principal.auth_token,
    )
