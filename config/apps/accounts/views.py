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
            