# apps/finance/services.py
from decimal import Decimal
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from apps.finance.models import Budget, CardAccount, Category, SavingsGoal, Transaction


def get_dashboard_cache_key(user_id, year: int = None, month: int = None) -> str:
    now = timezone.now()
    y = year or now.year
    m = month or now.month
    return f"dashboard:user:{user_id}:{y}:{m:02d}"


def invalidate_user_dashboard_cache(user_id) -> None:
    """Purges the current month's cached dashboard payload in Redis."""
    key = get_dashboard_cache_key(user_id)
    cache.delete(key)


@transaction.atomic
def create_transaction_atomic(
    *,
    user,
    category_id,
    description: str,
    amount: Decimal,
    transaction_type: str,
    date=None,
    card_id=None,
) -> Transaction:
    """
    Creates a transaction and updates the user's CardAccount balance inside
    a single PostgreSQL ACID transaction with row-level locking.
    """
    category = Category.objects.for_user(user).get(id=category_id)

    # Lock the primary or specified card row (`FOR UPDATE`) to prevent race conditions
    card_qs = CardAccount.objects.select_for_update().for_user(user)
    card = card_qs.filter(id=card_id).first() if card_id else card_qs.filter(is_primary=True).first()

    tx = Transaction.objects.create(
        user=user,
        card=card,
        category=category,
        description=description.strip(),
        amount=amount,
        transaction_type=transaction_type,
        status=Transaction.Status.COMPLETED,
        date=date or timezone.now().date(),
    )

    if card:
        if transaction_type == Transaction.TransactionType.INCOME:
            card.balance += amount
        else:
            card.balance -= amount
        card.save(update_fields=["balance"])

    # Bust Redis cache after DB commit succeeds
    transaction.on_commit(lambda: invalidate_user_dashboard_cache(user.id))
    return tx


def ensure_initial_finora_data(user) -> None:
    """
    Provisions a blank slate for new users by creating default empty categories
    (e.g., Food & Dining, Shopping, Transport, Income) with zero cards,
    zero goals, zero transactions, and absolutely zero fake money.
    """
    if Category.objects.for_user(user).exists():
        return

    cat_specs = [
        ("Food & Dining", Category.CategoryType.EXPENSE, "#6366F1", "bg-emerald-50 text-emerald-600", "utensils"),
        ("Shopping", Category.CategoryType.EXPENSE, "#EF4444", "bg-rose-50 text-rose-600", "shopping-bag"),
        ("Transport", Category.CategoryType.EXPENSE, "#38BDF8", "bg-indigo-50 text-indigo-600", "car"),
        ("Bills & Utilities", Category.CategoryType.EXPENSE, "#F59E0B", "bg-amber-50 text-amber-600", "zap"),
        ("Entertainment", Category.CategoryType.EXPENSE, "#10B981", "bg-teal-50 text-teal-600", "film"),
        ("Others", Category.CategoryType.EXPENSE, "#A855F7", "bg-purple-50 text-purple-600", "grid"),
        ("Income", Category.CategoryType.INCOME, "#22C55E", "bg-cyan-50 text-cyan-600", "briefcase"),
    ]

    with transaction.atomic():
        Category.objects.bulk_create([
            Category(
                user=user,
                name=name,
                category_type=ctype,
                color_hex=hex_c,
                badge_bg=badge,
                icon_name=icon,
            )
            for name, ctype, hex_c, badge, icon in cat_specs
        ])