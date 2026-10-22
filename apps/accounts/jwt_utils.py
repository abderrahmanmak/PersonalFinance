import uuid
from datetime import datetime, timezone
import jwt
from django.conf import settings
from django.core.cache import cache


def generate_tokens_for_user(user) -> dict:
    """Generates stateless Access and Refresh JWTs with unique JTI claims."""
    now = datetime.now(timezone.utc)
    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())

    access_payload = {
        "sub": str(user.id),
        "email": user.email,
        "full_name": user.get_full_name() or user.username,
        "is_premium": getattr(user, "is_premium", False),
        "type": "access",
        "jti": access_jti,
        "iat": now,
        "exp": now + settings.JWT_AUTH["ACCESS_TOKEN_LIFETIME"],
    }

    refresh_payload = {
        "sub": str(user.id),
        "type": "refresh",
        "jti": refresh_jti,
        "iat": now,
        "exp": now + settings.JWT_AUTH["REFRESH_TOKEN_LIFETIME"],
    }

    access_token = jwt.encode(
        access_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_AUTH["ALGORITHM"]
    )
    refresh_token = jwt.encode(
        refresh_payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_AUTH["ALGORITHM"]
    )

    return {"access": access_token, "refresh": refresh_token}


def decode_and_verify_token(token: str, expected_type: str = "access") -> dict | None:
    """Verifies JWT signature, expiration, type, and checks Redis Blacklist."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_AUTH["ALGORITHM"]],
        )
        if payload.get("type") != expected_type:
            return None

        # Check Redis Blacklist (O(1) lookup)
        jti = payload.get("jti")
        if jti and cache.get(f"blacklist:jti:{jti}"):
            return None

        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def blacklist_token(token: str) -> None:
    """Adds a token's JTI to Redis until its natural expiration timestamp."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_AUTH["ALGORITHM"]],
            options={"verify_exp": False},
        )
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            ttl = max(exp - now_ts, 0)
            if ttl > 0:
                cache.set(f"blacklist:jti:{jti}", "revoked", timeout=ttl)
    except jwt.InvalidTokenError:
        pass


def set_jwt_cookies(response, access_token: str, refresh_token: str = None):
    """Attaches HttpOnly, Secure, SameSite=Lax JWT cookies to any Django response."""
    secure_flag = not settings.DEBUG
    response.set_cookie(
        key=settings.JWT_AUTH["ACCESS_COOKIE_NAME"],
        value=access_token,
        max_age=int(settings.JWT_AUTH["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=secure_flag,
        samesite="Lax",
        path="/",
    )
    if refresh_token:
        response.set_cookie(
            key=settings.JWT_AUTH["REFRESH_COOKIE_NAME"],
            value=refresh_token,
            max_age=int(settings.JWT_AUTH["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            httponly=True,
            secure=secure_flag,
            samesite="Lax",
            path="/",
        )
    return response