# apps/finance/selectors.py
import json
from decimal import Decimal
from datetime import timedelta
from django.core.cache import cache
from django.db.models import Sum, F
from django.utils import timezone
from apps.finance.models import CardAccount, Category, SavingsGoal, Transaction
from apps.finance.services import get_dashboard_cache_key

def get_dashboard_payload(user, year: int = None, month: int = None) -> dict:
    """
    Retrieves the entire dashboard context from Redis.
    If empty, calculates all KPIs, charts, and table data, then caches it.
    """
    now = timezone.now().date()
    target_year = year or now.year
    target_month = month or now.month
    
    cache_key = get_dashboard_cache_key(user.id, target_year, target_month)
    cached_data = cache.get(cache_key)
    
    if cached_data:
        return cached_data

    # Define date ranges for current and previous month
    first_day_current = now.replace(year=target_year, month=target_month, day=1)
    if target_month == 12:
        first_day_next = now.replace(year=target_year + 1, month=1, day=1)
    else:
        first_day_next = now.replace(year=target_year, month=target_month + 1, day=1)

    if target_month == 1:
        first_day_prev = now.replace(year=target_year - 1, month=12, day=1)
    else:
        first_day_prev = now.replace(year=target_year, month=target_month - 1, day=1)
    
    last_day_prev = first_day_current - timedelta(days=1)

    # 1. Total Balance (Sum of all cards)
    total_balance = CardAccount.objects.for_user(user).aggregate(
        total=Sum('balance')
    )['total'] or Decimal('0.00')

    # 2. Monthly Income & Expenses (Current vs Previous)
    curr_txs = Transaction.objects.for_user(user).filter(
        date__gte=first_day_current,
        date__lt=first_day_next,
        status=Transaction.Status.COMPLETED
    )
    prev_txs = Transaction.objects.for_user(user).filter(
        date__gte=first_day_prev,
        date__lte=last_day_prev,
        status=Transaction.Status.COMPLETED
    )

    curr_income = curr_txs.filter(transaction_type=Transaction.TransactionType.INCOME).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    curr_expense = curr_txs.filter(transaction_type=Transaction.TransactionType.EXPENSE).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    
    prev_income = prev_txs.filter(transaction_type=Transaction.TransactionType.INCOME).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    prev_expense = prev_txs.filter(transaction_type=Transaction.TransactionType.EXPENSE).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    curr_savings = curr_income - curr_expense
    prev_savings = prev_income - prev_expense

    # MoM Calculations (ZeroDivisionError protected)
    def calc_mom(curr, prev):
        if prev == 0:
            if curr == 0:
                return 0.0
            return 100.0 if curr > 0 else -100.0
        pct = float(((curr - prev) / abs(prev)) * 100)
        return round(pct, 1)

    prev_balance = total_balance - curr_savings
    balance_mom = calc_mom(total_balance, prev_balance)

    # 3. Chart.js Data: Expense by Category (Donut)
    category_breakdown = list(
        curr_txs.filter(transaction_type=Transaction.TransactionType.EXPENSE)
        .values(name=F('category__name'), color=F('category__color_hex'))
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )
    donut_labels = [c['name'] for c in category_breakdown]
    donut_data = [float(c['total']) for c in category_breakdown]
    donut_colors = [c['color'] for c in category_breakdown]

    # 4. Chart.js Data: Spending Overview (Continuous 30-Day Timeline)
    thirty_days_ago = now - timedelta(days=29)
    daily_spending = list(
        Transaction.objects.for_user(user)
        .filter(date__gte=thirty_days_ago, date__lte=now, transaction_type=Transaction.TransactionType.EXPENSE)
        .values('date')
        .annotate(total=Sum('amount'))
        .order_by('date')
    )
    spending_by_date = {d['date']: float(d['total']) for d in daily_spending}
    line_labels = []
    line_data = []
    for i in range(29, -1, -1):
        day = now - timedelta(days=i)
        line_labels.append(day.strftime('%b %d'))
        line_data.append(spending_by_date.get(day, 0.0))

    # Assemble JSON-serializable dictionaries for the template
    payload = {
        "kpis": {
            "total_balance": float(total_balance),
            "balance_mom": balance_mom,
            "monthly_income": float(curr_income),
            "income_mom": calc_mom(curr_income, prev_income),
            "monthly_expense": float(curr_expense),
            "expense_mom": calc_mom(curr_expense, prev_expense),
            "savings": float(curr_savings),
            "savings_mom": calc_mom(curr_savings, prev_savings),
        },
        "charts": {
            "donut": json.dumps({"labels": donut_labels, "data": donut_data, "colors": donut_colors}),
            "line": json.dumps({"labels": line_labels, "data": line_data}),
        },
        "recent_transactions": list(
            Transaction.objects.for_user(user).select_related('category')[:5].values(
                'description', 'amount', 'date', 'transaction_type', 'status',
                'category__name', 'category__badge_bg', 'category__icon_name'
            )
        ),
        "goals": [
            {
                **g,
                "current_amount": float(g['current_amount']),
                "target_amount": float(g['target_amount']),
                "progress": min(int((g['current_amount'] / g['target_amount']) * 100), 100) if g['target_amount'] > 0 else 0
            }
            for g in SavingsGoal.objects.for_user(user).values(
                'title', 'current_amount', 'target_amount', 'icon_name', 'bar_color', 'icon_bg'
            )
        ],
        "cards": list(
            CardAccount.objects.for_user(user).values(
                'id', 'network', 'last_four', 'balance', 'is_primary', 'nickname'
            )
        ),
    }

    cache.set(cache_key, payload, timeout=3600)  # Cache for 1 hour
    return payload