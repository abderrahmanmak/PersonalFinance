import time
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpResponse
from apps.accounts.jwt_utils import (
    decode_and_verify_token,
    generate_tokens_for_user,
    set_jwt_cookies,
)

User = get_user_model

class RedisRateLimitMiddleware:
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = self._get_client_ip(request)
        path = request.path

        if path.startswith("/accounts/"):
            limit, window = 10 , 60  #10 req per 60s for auth 
            bucket = f"rl:auth:{ip}"
        else:
            limit, window = 120, 60 #120 req 60s for dashboard
            bucket = f"rl:general:{ip}"
        
        current_count = cache.get(bucket, 0)
        if current_count >= limit:
            return HttpResponse(
                "429 Too Many Requests - Rate limit exceeded. Please wait a moment.",
                status=429,
            )

        # Atomic increment in Redis with TTL
        if current_count == 0:
            cache.set(bucket, 1, timeout=window)
        else:
            try:
                cache.incr(bucket)
            except ValueError:
                cache.set(bucket, 1, timeout=window)

        return self.get_response(request)

    @staticmethod
    def _get_client_ip(request) -> str:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "0.0.0.0")



class JWTCookieAuthenticationMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request._new_access_token = None

        # Skip if already authenticated via Django admin / allauth session
        if not request.user.is_authenticated:
            access_token = request.COOKIES.get(settings.JWT_AUTH["ACCESS_COOKIE_NAME"])
            refresh_token = request.COOKIES.get(settings.JWT_AUTH["REFRESH_COOKIE_NAME"])

            payload = decode_and_verify_token(access_token, "access") if access_token else None

            if payload:
                user = self._get_cached_user(payload["sub"])
                if user:
                    request.user = user
            elif refresh_token:
                # Access token expired -> attempt silent rotation via Refresh Token
                refresh_payload = decode_and_verify_token(refresh_token, "refresh")
                if refresh_payload:
                    user = self._get_cached_user(refresh_payload["sub"])
                    if user:
                        request.user = user
                        tokens = generate_tokens_for_user(user)
                        request._new_access_token = tokens["access"]

        response = self.get_response(request)

        # Attach rotated access token cookie if refreshed during this request
        if getattr(request, "_new_access_token", None):
            set_jwt_cookies(response, request._new_access_token)

        return response

    @staticmethod
    def _get_cached_user(user_id: str):
        cache_key = f"user:obj:{user_id}"
        user = cache.get(cache_key)
        if not user:
            user = User.objects.filter(id=user_id, is_active=True).first()
            if user:
                cache.set(cache_key, user, timeout=300)  # Cache user instance for 5 mins
        return user


class ContentSecurityPolicyMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://unpkg.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: https://images.unsplash.com https://i.pravatar.cc",
            "connect-src 'self'",
            "frame-ancestors 'none'",
        ]
        response["Content-Security-Policy"] = "; ".join(csp_directives)
        return response