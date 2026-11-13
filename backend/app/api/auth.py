from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from app.api.deps import CipherDep, DBDep, HttpDep, OptionalUser, SettingsDep
from app.auth import pkce
from app.auth.security import sign, unsign
from app.auth.sessions import (
    OAUTH_COOKIE,
    SESSION_COOKIE,
    create_session,
    end_session,
    exchange_code,
    save_tokens,
)
from app.db.models import User
from app.services.live import delete_user_data
from app.spotify.client import API_BASE, SpotifyError

router = APIRouter(tags=["auth"])
OAUTH_MAX_AGE = 600


def _frontend(settings: SettingsDep, path: str, **params: str) -> str:
    query = f"?{urlencode(params)}" if params else ""
    return f"{settings.frontend_url.rstrip('/')}{path}{query}"


@router.get("/api/auth/spotify/start")
def start(settings: SettingsDep) -> RedirectResponse:
    if not settings.spotify_client_id:
        raise HTTPException(status_code=503, detail="Spotify is not configured on this server")
    state, verifier = pkce.new_state(), pkce.code_verifier()
    resp = RedirectResponse(
        pkce.authorize_url(settings.spotify_client_id, settings.spotify_redirect_uri, state, verifier),
        status_code=307,
    )
    resp.set_cookie(
        OAUTH_COOKIE,
        sign(settings.secret(), {"state": state, "verifier": verifier}),
        max_age=OAUTH_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )
    return resp


@router.get("/api/auth/spotify/callback")
async def callback(
    request: Request,
    settings: SettingsDep,
    db: DBDep,
    cipher: CipherDep,
    http: HttpDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    def fail(reason: str) -> RedirectResponse:
        r = RedirectResponse(_frontend(settings, "/settings", auth_error=reason), status_code=303)
        r.delete_cookie(OAUTH_COOKIE, path="/")
        return r

    saved = unsign(settings.secret(), request.cookies.get(OAUTH_COOKIE), OAUTH_MAX_AGE)
    if error:
        return fail("denied" if error == "access_denied" else "spotify_error")
    if not saved or not code or not pkce.states_match(saved.get("state"), state):
        return fail("state_mismatch")

    try:
        tokens = await exchange_code(http, settings, code, str(saved["verifier"]))
        me_resp = await http.get(
            f"{API_BASE}/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
    except SpotifyError:
        return fail("token_exchange")
    if me_resp.status_code == 403:
        return fail("not_allowlisted")
    if me_resp.status_code != 200:
        return fail("profile")
    me = me_resp.json()

    user = db.scalar(select(User).where(User.spotify_user_id == me["id"]))
    if user is None:
        user = User(spotify_user_id=me["id"], display_name=me.get("display_name"))
        db.add(user)
    else:
        user.display_name = me.get("display_name")
    db.commit()
    save_tokens(db, user, cipher, tokens)
    token = create_session(db, user, settings)

    resp = RedirectResponse(_frontend(settings, "/dashboard"), status_code=303)
    resp.delete_cookie(OAUTH_COOKIE, path="/")
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )
    return resp


@router.get("/api/auth/me")
def me(user: OptionalUser, settings: SettingsDep) -> dict[str, object]:
    return {
        "spotify_configured": settings.spotify_enabled,
        "connected": user is not None,
        "display_name": user.display_name if user else None,
    }


@router.post("/api/auth/logout")
def logout(request: Request, db: DBDep) -> Response:
    end_session(db, request.cookies.get(SESSION_COOKIE))
    resp = Response(status_code=204)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@router.delete("/api/me")
def delete_me(user: OptionalUser, db: DBDep) -> Response:
    """Disconnect Spotify and delete everything stored about this user."""
    if user is not None:
        delete_user_data(db, user)
    resp = Response(status_code=204)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp
