from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone


class ShopUserManager(BaseUserManager):
    def create_user(self, username: str, password: str | None = None, **extra_fields):
        if not username:
            raise ValueError("Username must be set")
        if not password:
            raise ValueError("Password must be set")

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
    contact_phone = models.CharField(max_length=50, blank=True)
    contact_email = models.EmailField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    must_change_password = models.BooleanField(default=True)
    wallet_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=5)
    max_stake = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    feature_flags = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    objects = ShopUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self):
        return f"{self.name} ({self.username})"

    def save(self, *args, **kwargs):
        # Keep Django's is_active flag aligned with the business status.
        self.is_active = self.status == self.Status.ACTIVE
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
