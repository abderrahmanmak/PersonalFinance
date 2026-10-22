# apps/finance/tests.py
from decimal import Decimal
from django.test import TestCase, Client
from django.utils import timezone
from apps.accounts.models import User
from apps.finance.models import CardAccount, Category, SavingsGoal, Transaction
from apps.finance.services import ensure_initial_finora_data
from apps.finance.selectors import get_dashboard_payload


class FinoraDynamicAuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dynamic_tester",
            email="tester@finora.test",
            password="securepassword123",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_model_defaults_are_not_hardcoded_placeholders(self):
        """Ensures user and card account models do not store hardcoded mock defaults."""
        # User defaults
        self.assertEqual(self.user.full_name, "")
        self.assertFalse(self.user.is_premium)
        self.assertEqual(self.user.avatar_url, "")

        # CardAccount defaults
        card = CardAccount.objects.create(
            user=self.user,
            nickname="Test Card",
            last_four="1234",
        )
        self.assertEqual(card.balance, Decimal("0.00"))
        self.assertFalse(card.is_primary)

    def test_ensure_initial_finora_data_provisions_blank_slate_only(self):
        """
        Ensures initial setup creates only default empty categories,
        with 0 cards, 0 transactions, 0 goals, and $0 fake money.
        """
        ensure_initial_finora_data(self.user)

        # 7 default categories should exist
        categories = Category.objects.for_user(self.user)
        self.assertEqual(categories.count(), 7)

        # Zero fake cards, goals, or transactions
        self.assertEqual(CardAccount.objects.for_user(self.user).count(), 0)
        self.assertEqual(SavingsGoal.objects.for_user(self.user).count(), 0)
        self.assertEqual(Transaction.objects.for_user(self.user).count(), 0)

    def test_graceful_empty_states_in_selectors(self):
        """
        Ensures get_dashboard_payload cleanly handles a user with $0
        and 0 transactions without division-by-zero errors.
        """
        ensure_initial_finora_data(self.user)
        payload = get_dashboard_payload(self.user)

        kpis = payload["kpis"]
        self.assertEqual(kpis["total_balance"], 0.0)
        self.assertEqual(kpis["balance_mom"], 0.0)
        self.assertEqual(kpis["monthly_income"], 0.0)
        self.assertEqual(kpis["income_mom"], 0.0)
        self.assertEqual(kpis["monthly_expense"], 0.0)
        self.assertEqual(kpis["expense_mom"], 0.0)
        self.assertEqual(kpis["savings"], 0.0)
        self.assertEqual(kpis["savings_mom"], 0.0)

        # Chart datasets
        self.assertEqual(payload["cards"], [])
        self.assertEqual(payload["goals"], [])
        self.assertEqual(payload["recent_transactions"], [])

    def test_dashboard_template_renders_empty_state_without_hardcoded_data(self):
        """Verifies dashboard template displays no mock names, avatars, or static percentages."""
        response = self.client.get("/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        # Verify hardcoded static strings from original mockup are gone
        self.assertNotIn("Ayesha Rahman", content)
        self.assertNotIn("https://i.pravatar.cc", content)
        self.assertNotIn("12% <span class=\"text-gray-400 font-normal\">vs last month</span>", content)

        # Verify dynamic empty state messaging
        self.assertIn("No Linked Cards", content)
        self.assertIn("No savings goals yet", content)
        self.assertIn("No recent transactions recorded", content)

    def test_transactions_template_renders_graceful_empty_state(self):
        """Verifies transactions template displays graceful empty state."""
        response = self.client.get("/transactions/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        self.assertIn("No transactions found", content)
