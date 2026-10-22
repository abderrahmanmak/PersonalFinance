# apps/accounts/views.py
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from apps.accounts.jwt_utils import (
    blacklist_token,
    generate_tokens_for_user,
    set_jwt_cookies,
)

@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect ("finance:dashboard")

    error = None
    if request.method == "POST":
        email = request.POST.get("email" , "").strip().lower()
        password = request.POST.get("password" , "")
        
        user = authenticate(request, email=email , password=password)

        if user is not None:
            login(request , user)
            tokens = generate_tokens_for_user(user)
            response = redirect("finance:dashboard")
            return set_jwt_cookies(response, tokens["access"] , tokens["refresh"])
        error = "Invalid email or password"

    return render(request, "accounts/login.html" , {"error":error}) 

@require_http_methods(["POST"])
def logout_view(request):
    access_token = request.COOKIES.get(settings.JWT_AUTH["ACCESS_COOKIE_NAME"])
    refresh_token = request.COOKIES.get(settings.JWT_AUTH["REFRESH_COOKIE_NAME"])

    if access_token:
        blacklist_token(access_token)
    if refresh_token:
        blacklist_token(refresh_token)

    logout(request)
    response = redirect("account_login")
    response.delete_cookie(settings.JWT_AUTH["ACCESS_COOKIE_NAME"])
    response.delete_cookie(settings.JWT_AUTH["REFRESH_COOKIE_NAME"])
    return response