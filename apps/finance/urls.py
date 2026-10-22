from django.urls import path
from apps.finance import views

app_name = "finance"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("transactions/", views.transactions_view, name="transactions"),
    path("budgets/", views.placeholder_view, name="budgets"),
    path("goals/", views.placeholder_view, name="goals"),
    path("analytics/", views.placeholder_view, name="analytics"),
    path("cards/", views.placeholder_view, name="cards"),
    path("reports/", views.placeholder_view, name="reports"),
    
    # Quick Actions
    path("transaction/add/", views.add_transaction_view, name="add_transaction"),
    path("search/", views.search_transactions_view, name="search"),
]