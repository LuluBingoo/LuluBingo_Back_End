import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def generate_default_shop_code() -> str:
    return f"shop-{uuid.uuid4().hex[:8]}"


class ShopUserManager(BaseUserManager):
    def create_user(self, username: str, password: str | None = None, **extra_fields):
        if not username:
            raise ValueError("Username must be set")
        if not password:
            raise ValueError("Password must be set")
        if not extra_fields.get("contact_email"):
            raise ValueError("Contact email must be set")

        username = username.lower()
        name = extra_fields.pop("name", username)
        extra_fields.setdefault("name", name)
        extra_fields.setdefault("status", ShopUser.Status.PENDING)
        extra_fields.setdefault("feature_flags", {})

        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.must_change_password = extra_fields.get("must_change_password", True)
        user.save(using=self._db)
        return user

    def create_superuser(self, username: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("status", ShopUser.Status.ACTIVE)
        extra_fields.setdefault("must_change_password", False)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, password, **extra_fields)


class ShopUser(AbstractBaseUser, PermissionsMixin):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        BLOCKED = "blocked", "Blocked"

    username = models.CharField(max_length=150, unique=True)
    name = models.CharField(max_length=255, default="New Shop")
    shop_code = models.SlugField(max_length=60, unique=True, editable=False, default=generate_default_shop_code)
    contact_phone = models.CharField(max_length=50, blank=True)
    contact_email = models.EmailField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    must_change_password = models.BooleanField(default=True)
    wallet_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=5)
    max_stake = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    feature_flags = models.JSONField(default=dict, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_name = models.CharField(max_length=120, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    profile_completed = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_method = models.CharField(
        max_length=20,
        choices=[("totp", "Authenticator app")],
        default="totp",
    )
    totp_secret = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    objects = ShopUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = ["contact_email"]

    def __str__(self):
        return f"{self.name} ({self.username})"

    def _ensure_shop_code(self):
        base = slugify(self.name or self.username or "shop") or "shop"
        if self.shop_code and not (
            self.shop_code.startswith("shop-") and len(self.shop_code) == len("shop-") + 8
        ):
            return

        candidate = base
        suffix = 1
        while type(self).objects.filter(shop_code=candidate).exclude(pk=self.pk).exists():
            suffix += 1
            candidate = f"{base}-{suffix}"
        self.shop_code = candidate

    def ensure_totp_secret(self):
        if self.totp_secret:
            return
        # 32-character base32 secret compatible with Google Authenticator
        from pyotp import random_base32

        self.totp_secret = random_base32()

    def save(self, *args, **kwargs):
        # Keep Django's is_active flag aligned with the business status.
        self.is_active = self.status == self.Status.ACTIVE
        self._ensure_shop_code()
        super().save(*args, **kwargs)


class LoginAttempt(models.Model):
    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user = models.ForeignKey(ShopUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="login_attempts")
    success = models.BooleanField(default=False)
    timestamp = models.DateTimeField(default=timezone.now)
    user_agent = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        status = "success" if self.success else "failure"
        return f"{self.username} {status} @ {self.timestamp:%Y-%m-%d %H:%M:%S}"
