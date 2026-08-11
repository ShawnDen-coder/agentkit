"""FastAPI BI example backend: SSE ``/v1/query`` + auth seam + FakeOrchestrator.

Run (from repo root, after `uv sync --all-packages` + `uv pip install fastapi uvicorn`):

    uv run python example/fastapi-bi/backend.py

Then open http://127.0.0.1:8000 in a browser.

This shows the C&S (client/server) deployment: a browser frontend talks to the
FastAPI backend over the SSE wire protocol. Auth runs BEFORE the SSE path
(transport-agnostic seam); the orchestrator's ``BaseSSE`` events are serialized
via ``to_sse()`` into ``event:`` / ``data:`` frames.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path


# Make `from fake_orchestrator import FakeOrchestrator` resolve from example/_common.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

import uvicorn
from bi_adapter import MockBiAdapter
from fake_orchestrator import FakeOrchestrator
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse

from agentkit_protocol import AllowAllAuthorizer
from agentkit_protocol import AuthContext
from agentkit_protocol import AuthenticationError
from agentkit_protocol import AuthzAction
from agentkit_protocol import Message
from agentkit_protocol import Principal
from agentkit_protocol import QueryRequest
from agentkit_protocol import session_from_principal
from agentkit_protocol.auth import Authenticator


# ---------------------------------------------------------------------------
# Auth seam (transport-agnostic). Real impl: JWT / OAuth2 / API-key / SSO.
# ---------------------------------------------------------------------------


class ExampleAuthenticator:
    """Trivial: accepts any ``Bearer <token>`` and derives a Principal.

    A real impl reads the credential from ``AuthContext`` (header/cookie/cert),
    verifies it (JWKS, introspection, ...), and returns a Principal with the
    user's identity + permissions + a delegated backend-fetch credential. The
    same Authenticator works for the DCC profile (studio session) - it never sees
    an HTTP type.
    """

    async def authenticate(self, context: AuthContext) -> Principal:
        """Verify the bearer token and return the Principal (raise on failure)."""
        auth = context.header("Authorization")
        if not auth or not auth.startswith("Bearer "):
            raise AuthenticationError("missing bearer token")
        token = auth.removeprefix("Bearer ").strip()
        return Principal(
            user_identity=f"user-{token[:6]}",
            user_permissions=("bi:read",),
            workspace_id="ws-example",
            auth_token=token,
        )


async def _auth_context(request: Request) -> AuthContext:
    """Bridge the FastAPI Request onto the transport-agnostic AuthContext."""
    return AuthContext(
        headers=dict(request.headers),
        query=dict(request.query_params),
        cookies=dict(request.cookies),
        peer={"remote_addr": request.client.host if request.client else None},
    )


# ---------------------------------------------------------------------------
# App wiring: adapter + orchestrator + auth. (agentkit-runtime swaps in here.)
# ---------------------------------------------------------------------------


adapter = MockBiAdapter()
orchestrator = FakeOrchestrator(adapter)
authenticator: Authenticator = ExampleAuthenticator()
authorizer = AllowAllAuthorizer()  # real impl: per-verb RLS

app = FastAPI(title="agentkit FastAPI BI example")
_STATIC = Path(__file__).resolve().parent / "static"


@app.get("/")
async def index() -> FileResponse:
    """Serve the chat UI."""
    return FileResponse(_STATIC / "index.html")


@app.post("/v1/query")
async def query(request: Request) -> StreamingResponse:
    """SSE endpoint: auth -> SessionContext -> orchestrator.run -> SSE stream."""
    # 1. Auth runs before the SSE/orchestrator path (not part of either waist).
    ctx = await _auth_context(request)
    principal = await authenticator.authenticate(ctx)
    await authorizer.authorize(principal, AuthzAction(verb="query"))

    # 2. Build the wire QueryRequest. The frontend sends {messages}; the backend is
    #    authoritative for session_context - identity / permissions / trace_id come
    #    from the verified Principal, and auth_token rides the Authorization header
    #    (never the body). So we do NOT validate the body as a QueryRequest (its
    #    session_context would be incomplete); we wrap messages with the auth-derived
    #    session.
    body = await request.json()
    messages = [Message.model_validate(m) for m in body.get("messages", [])]
    session = session_from_principal(principal, trace_id=str(uuid.uuid4()))
    req = QueryRequest(messages=messages, session_context=session)

    # 3. Drive the orchestrator; serialize each BaseSSE event to an SSE frame.
    async def stream() -> AsyncIterator[str]:
        async for event in orchestrator.run(req):
            payload = event.to_sse()
            yield f"event: {payload['event']}\ndata: {payload['data']}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
