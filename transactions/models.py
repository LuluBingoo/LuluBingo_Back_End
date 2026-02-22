from django.conf import settings
from django.db import models
from django.utils import timezone


class Transaction(models.Model):
    class Type(models.TextChoices):
        DEPOSIT = "deposit", "Deposit"
        WITHDRAWAL = "withdrawal", "Withdrawal"
        BET_DEBIT = "bet_debit", "Bet debit"
        BET_CREDIT = "bet_credit", "Bet credit"
        ADJUSTMENT = "adjustment", "Adjustment"

    class ActorRole(models.TextChoices):
        SHOP = "shop", "Shop"
        ADMIN = "admin", "Admin"
        SYSTEM = "system", "System"

    class Currency(models.TextChoices):
        ETB = "ETB", "ETB"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="transactions", on_delete=models.CASCADE)
    tx_type = models.CharField(max_length=30, choices=Type.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=120, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    actor_role = models.CharField(max_length=20, choices=ActorRole.choices, default=ActorRole.SHOP)
    currency = models.CharField(max_length=10, choices=Currency.choices, default=Currency.ETB)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="transaction_user_id_386a11_idx"),
            models.Index(fields=["user", "tx_type", "-created_at"], name="tx_user_type_created_idx"),
        ]

    def __str__(self):
        return f"{self.tx_type} {self.amount} for {self.user.username}"
