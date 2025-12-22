from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone


class ShopUserManager(BaseUserManager):
    def create_user(self, username: str, password: str | None = None, **extra_fields):
        if not username:
            raise ValueError("Username must be set")
        username = username.lower()
        user = self.model(username=username, **extra_fields)
        if password:
            user.set_password(password)
        else:
            raise ValueError("Password must be set")
        user.save(using=self._db)
        return user

    def create_superuser(self, username: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, password, **extra_fields)


class ShopUser(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    objects = ShopUserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self):
        return self.username


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
