# apps/finance/views.py
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
# ADDED 'Transaction' TO THE IMPORT BELOW:
from apps.finance.models import Category, Transaction
from apps.finance.selectors import get_dashboard_payload
from apps.finance.services import create_transaction_atomic, ensure_initial_finora_data

@login_required
@require_http_methods(["GET"])
def dashboard_view(request):
    """Renders the main Finora dashboard."""
    ensure_initial_finora_data(request.user)
    payload = get_dashboard_payload(request.user)
    categories = Category.objects.for_user(request.user)

    context = {
        "payload": payload,
        "categories": categories,
    }
    return render(request, "finance/dashboard.html", context)

# ADDED MISSING VIEWS HERE:
@login_required
@require_http_methods(["GET"])
def transactions_view(request):
    """Full-page ledger view displaying all user transactions from SQLite."""
    transactions = Transaction.objects.for_user(request.user).select_related('category', 'card')
    
    return render(request, "finance/transactions.html", {
        "transactions": transactions
    })

@login_required
def placeholder_view(request):
    """Temporary view for unbuilt sidebar pages."""
    page_name = request.resolver_match.url_name.title()
    if page_name == "Add_Transaction":
        page_name = "Add Transaction"
    return render(request, "finance/placeholder.html", {"page_name": page_name})

@login_required
@require_http_methods(["POST"])
def add_transaction_view(request):
    """Handles the '+ Add Transaction' form submission."""
    category_id = request.POST.get("category_id")
    description = request.POST.get("description")
    amount = request.POST.get("amount")
    transaction_type = request.POST.get("transaction_type", "EXPENSE")
    date = request.POST.get("date")

    try:
        create_transaction_atomic(
            user=request.user,
            category_id=category_id,
            description=description,
            amount=Decimal(amount),
            transaction_type=transaction_type,
            date=date if date else None,
        )
        if request.headers.get('HX-Request'):
            return render(request, "finance/partials/recent_transactions.html", {
                "recent_transactions": get_dashboard_payload(request.user)["recent_transactions"]
            })
    except Exception as e:
        pass 

    return redirect("finance:dashboard")

@login_required
@require_http_methods(["GET"])
def search_transactions_view(request):
    """Provides JSON results for the 'Search anything...' top nav bar."""
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"results": []})
        
    results = request.user.transactions.filter(
        description__icontains=query
    ).select_related('category').order_by('-date')[:5]
    
    data = [{
        "description": tx.description,
        "amount": str(tx.amount),
        "date": tx.date.strftime("%Y-%m-%d"),
        "category": tx.category.name,
    } for tx in results]
    
    return JsonResponse({"results": data})