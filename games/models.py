import random

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Game(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    shop = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="games", on_delete=models.CASCADE)
    game_code = models.SlugField(max_length=40, unique=True, editable=False)
    bet_amount = models.DecimalField(max_digits=12, decimal_places=2)
    num_players = models.PositiveSmallIntegerField()
    win_amount = models.DecimalField(max_digits=12, decimal_places=2)
    cartella_numbers = models.JSONField(default=list)  # list of cartella number lists
    cartella_draw_sequences = models.JSONField(default=list)  # per-cartella shuffled draw order
    draw_sequence = models.JSONField(default=list)  # master shuffled draw order
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    winners = models.JSONField(default=list, blank=True)  # indices of winning cartella(s)
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Game {self.game_code} ({self.shop.username})"

    def _ensure_game_code(self):
        if self.game_code:
            return
        base = slugify(getattr(self.shop, "shop_code", None) or self.shop.username) or "game"
        suffix = random.randint(1000, 9999)
        candidate = f"{base}-{suffix}"
        while type(self).objects.filter(game_code=candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix}"
        self.game_code = candidate

    def _ensure_draws(self):
        if not self.draw_sequence:
            self.draw_sequence = random.sample(range(1, 76), 75)
        if not self.cartella_draw_sequences:
            self.cartella_draw_sequences = [random.sample(range(1, 76), 75) for _ in self.cartella_numbers]

    def save(self, *args, **kwargs):
        self._ensure_game_code()
        self._ensure_draws()
        super().save(*args, **kwargs)
