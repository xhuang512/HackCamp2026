"""Who is calling.

Every route that needs a student depends on current_user(). Behind it are two
kinds of bearer token, and the rest of the app cannot tell them apart:

  Auth0 access token   Verified against Auth0's public keys. `sub` is the
                       identity; students.auth_sub is the only thing we store
                       about it. We never see or keep the email address.
  Guest token          Issued by POST /students in demo mode only. Signed with
                       GUEST_TOKEN_SECRET so a guest cannot mint one for
                       another guest's student id.

Both arrive in the Authorization header, never a cookie: the frontend and
backend sit on different domains and Safari blocks cross-site cookies.

Three dependencies, so a route says what it needs rather than re-checking:

  current_user()           the student, or 401
  current_user_optional()  the student or None, for routes that work either way
  onboarded_user()         the student, or 401, or 403 if they have no profile
"""

import hmac
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config, store

# auto_error=False so a missing header reaches our code and the public routes
# keep working. FastAPI's default would 403 before the route is entered.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sign in to do that.",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass
class Caller:
    """A verified token's holder, before we know whether they have a profile.

    Onboarding needs this: a student who has signed in but not finished
    onboarding has an identity and no student row, and GET /me's whole job is
    to say so.
    """

    auth_sub: str
    is_guest: bool
    student: store.Student | None


# ---------------------------------------------------------------- guest tokens


def issue_guest_token(student_id: str) -> str:
    """`guest.<student_id>.<expiry>.<signature>`.

    Not a JWT. A JWT here would mean a second verification path with its own
    library options to get wrong, for a token that carries one id and an
    expiry. The signature is over the id and the expiry together, so neither
    can be edited on its own.
    """
    expires_at = int(time.time()) + config.GUEST_TOKEN_HOURS * 3600
    payload = f"{student_id}.{expires_at}"
    return f"guest.{payload}.{_sign(payload)}"


def _sign(payload: str) -> str:
    return hmac.new(
        config.GUEST_TOKEN_SECRET.encode(), payload.encode(), sha256
    ).hexdigest()


def _read_guest_token(token: str) -> str | None:
    """The student id a guest token names, or None if it is not a valid one."""
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "guest":
        return None
    _, student_id, expires_at, signature = parts

    # compare_digest, not ==, so a wrong signature takes the same time to
    # reject however many leading characters it got right.
    if not hmac.compare_digest(signature, _sign(f"{student_id}.{expires_at}")):
        return None
    try:
        if int(expires_at) < time.time():
            return None
    except ValueError:
        return None
    return student_id


# ---------------------------------------------------------------- Auth0


_jwks_client: jwt.PyJWKClient | None = None


def _jwks() -> jwt.PyJWKClient:
    """Auth0's public keys. PyJWKClient caches them, so this is one network
    call per key per process, not one per request."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(
            f"https://{config.AUTH0_DOMAIN}/.well-known/jwks.json"
        )
    return _jwks_client


def check_auth0_reachable() -> str | None:
    """Fetch Auth0's signing keys once, now. None means they came back.

    This is a setup aid, not a health check. Every way of getting the Auth0
    config wrong looks identical from a phone, which is one silent 401, so the
    server says which part is broken at boot instead.
    """
    if not config.AUTH0_READY:
        return "AUTH0_DOMAIN or AUTH0_AUDIENCE is not set"
    try:
        _jwks().fetch_data()
    except Exception as cause:  # noqa: BLE001 - any failure is the same answer
        return f"could not read https://{config.AUTH0_DOMAIN}/.well-known/jwks.json ({cause})"
    return None


def _read_auth0_token(token: str) -> str | None:
    """The `sub` an Auth0 access token names, or None if it does not verify.

    The audience and issuer checks are not optional. A signature check alone
    accepts a valid token that was issued for a different API, which is a
    token this backend has no business trusting.
    """
    if not config.AUTH0_READY:
        return None
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=config.AUTH0_ALGORITHMS,
            audience=config.AUTH0_AUDIENCE,
            issuer=f"https://{config.AUTH0_DOMAIN}/",
        )
    except jwt.PyJWTError:
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) else None


# ---------------------------------------------------------------- dependencies


def current_caller(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Caller | None:
    """Verify the token, if there is one. None means unauthenticated, which is
    fine for public routes and an error for everything else."""
    if credentials is None:
        return None
    token = credentials.credentials

    # Guest tokens carry their own prefix, so there is no guessing and no
    # chance of running an Auth0 token through the guest path.
    if token.startswith("guest."):
        if not config.DEMO_MODE:
            return None
        student_id = _read_guest_token(token)
        if student_id is None:
            return None
        student = store.get(student_id)
        if student is None:
            return None
        return Caller(auth_sub=f"guest:{student_id}", is_guest=True, student=student)

    auth_sub = _read_auth0_token(token)
    if auth_sub is None:
        return None
    return Caller(
        auth_sub=auth_sub, is_guest=False, student=store.get_by_sub(auth_sub)
    )


def current_user_optional(
    caller: Annotated[Caller | None, Depends(current_caller)],
) -> store.Student | None:
    if caller is None or caller.student is None or not caller.student.onboarded:
        return None
    return caller.student


def current_user(
    caller: Annotated[Caller | None, Depends(current_caller)],
) -> Caller:
    """The verified caller, profile or not. 401 without a usable token.

    Returns the Caller rather than the Student because GET /me and
    POST /students both run before a profile exists.
    """
    if caller is None:
        raise _UNAUTHENTICATED
    return caller


def onboarded_user(
    caller: Annotated[Caller, Depends(current_user)],
) -> store.Student:
    """For every route that needs a profile. 403, not 401: the token is fine,
    the profile is missing, and retrying the login will not fix it."""
    if caller.student is None or not caller.student.onboarded:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Finish setting up your profile first.",
        )
    return caller.student


# ------------------------------------------------- compatibility with the
# Supabase routers
#
# routers/groups.py and routers/students.py were written against the earlier
# guest-only auth module, which exposed get_current_student_id() and
# create_guest_session(). Those names are kept here so the Supabase side keeps
# working unchanged. AGENTS.md names current_user() as the real entry point,
# so prefer it in new code; these two are a bridge, not an interface.


def get_current_student_id(
    student: Annotated[store.Student, Depends(onboarded_user)],
) -> str:
    """The signed-in student's id, for routes that only need the id.

    Goes through onboarded_user, so a token belonging to someone who has not
    finished onboarding is a 403 rather than a lookup against an id that has
    no profile.
    """
    return student.id


def create_guest_session(student_id: str) -> str:
    """Old name for issue_guest_token.

    Unlike the version it replaces, the returned token only verifies while a
    student with this id exists, because current_caller looks the row up. A
    test that mints a token for an invented id has to put that id in the store
    first.
    """
    return issue_guest_token(student_id)


def ensure_guest_sessions_configured() -> None:
    """A no-op now, kept so the Supabase routers' import still resolves.

    config.GUEST_TOKEN_SECRET always holds a value, falling back to a random
    one per process, so guest signing can no longer be unconfigured at
    runtime. GET /auth/config reports whether it came from the environment,
    which is the thing worth knowing on a deployment.
    """
    return None
