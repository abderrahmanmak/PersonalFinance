# apps/finance/models.py
import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class OwnedByUserQuerySet(models.QuerySet):
    """Row-level security helper: strictly scopes queries to the authenticated user."""

    def for_user(self, user):
        return self.filter(user=user)


class CardAccount(models.Model):
    """
    Represents the dark right-side card widget in Finora:
    e.g., VISA | Personal Card | **** 4521 | Available Balance: $2,450.00
    """

    class CardNetwork(models.TextChoices):
        VISA = "VISA", "Visa"
        MASTERCARD = "MASTERCARD", "Mastercard"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cards"
    )
    nickname = models.CharField(max_length=50)
    network = models.CharField(
        max_length=15, choices=CardNetwork.choices, default=CardNetwork.VISA
    )
    last_four = models.CharField(max_length=4)
    balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedByUserQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["user", "is_primary"]),
        ]

    def __str__(self):
        return f"{self.network} •••• {self.last_four} (${self.balance})"


class Category(models.Model):
    """
    Drives both the 'Expense by Category' Donut Chart and the colored pills
    in the 'Recent Transactions' table.
    """

    class CategoryType(models.TextChoices):
        INCOME = "INCOME", "Income"
        EXPENSE = "EXPENSE", "Expense"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField(max_length=60)  # e.g., "Food & Dining", "Transport"
    category_type = models.CharField(
        max_length=10, choices=CategoryType.choices, default=CategoryType.EXPENSE
    )
    color_hex = models.CharField(max_length=7, default="#6366F1")  # Chart & dot color
    badge_bg = models.CharField(max_length=30, default="bg-emerald-50 text-emerald-600")
    icon_name = models.CharField(max_length=40, default="shopping-bag")

    objects = OwnedByUserQuerySet.as_manager()

    class Meta:
        unique_together = ("user", "name")
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Transaction(models.Model):
    """
    Core ledger record. Drives KPI cards, 30-day Spending Overview chart,
    Expense by Category donut, and Recent Transactions table.
    """

    class TransactionType(models.TextChoices):
        INCOME = "INCOME", "Income"
        EXPENSE = "EXPENSE", "Expense"

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Completed"
        PENDING = "PENDING", "Pending"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions"
    )
    card = models.ForeignKey(
        CardAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="transactions"
    )
    description = models.CharField(max_length=140)  # e.g., "Starbucks Coffee"
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    transaction_type = models.CharField(
        max_length=10, choices=TransactionType.choices, default=TransactionType.EXPENSE
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.COMPLETED
    )
    date = models.DateField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedByUserQuerySet.as_manager()

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["user", "-date", "-created_at"]),
            models.Index(fields=["user", "transaction_type", "date"]),
        ]

    def __str__(self):
        sign = "+" if self.transaction_type == self.TransactionType.INCOME else "-"
        return f"{self.description}: {sign}${self.amount}"


class Budget(models.Model):
    """Quick Link: 'Set Budget' monthly category cap."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets"
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="budgets"
    )
    monthly_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    month = models.DateField(help_text="First day of the target month (YYYY-MM-01)")

    objects = OwnedByUserQuerySet.as_manager()

    class Meta:
        unique_together = ("user", "category", "month")


class SavingsGoal(models.Model):
    """
    Drives the right-side 'Goals' widget in the screenshot:
    - Emergency Fund ($1,000 / $3,000 -> 33%)
    - Travel Fund ($600 / $2,000 -> 30%)
    - New Laptop ($800 / $1,500 -> 53%)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="goals"
    )
    title = models.CharField(max_length=80)
    current_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    target_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    icon_name = models.CharField(max_length=40, default="shield-check")
    bar_color = models.CharField(max_length=30, default="bg-emerald-500")
    icon_bg = models.CharField(max_length=40, default="bg-emerald-50 text-emerald-600")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OwnedByUserQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]

    @property
    def progress_percentage(self) -> int:
        if self.target_amount <= 0:
            return 0
        pct = int((self.current_amount / self.target_amount) * 100)
        return min(pct, 100)