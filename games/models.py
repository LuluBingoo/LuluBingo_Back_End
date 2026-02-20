import random
import string

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Game(models.Model):
    class Mode(models.TextChoices):
        STANDARD = "standard", "Standard"
        SHOP_FIXED4 = "shop_fixed4", "Shop Fixed 4"

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
    called_numbers = models.JSONField(default=list, blank=True)
    call_cursor = models.PositiveSmallIntegerField(default=0)
    current_called_number = models.PositiveSmallIntegerField(null=True, blank=True)
    game_mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.STANDARD)
    cartella_number_map = models.JSONField(default=dict, blank=True)  # cartellaNumber(string)->index
    shop_players_data = models.JSONField(default=list, blank=True)
    min_bet_per_cartella = models.DecimalField(max_digits=12, decimal_places=2, default=20)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    winners = models.JSONField(default=list, blank=True)  # indices of winning cartella(s)
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    bet_debited_at = models.DateTimeField(null=True, blank=True)
    payout_credited_at = models.DateTimeField(null=True, blank=True)
    refund_credited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Game {self.game_code} ({self.shop.username})"

    def _ensure_game_code(self):
        if self.game_code:
            return
        if self.game_mode == self.Mode.SHOP_FIXED4:
            candidate = f"BINGO-{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"
            while type(self).objects.filter(game_code=candidate).exists():
                candidate = f"BINGO-{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"
            self.game_code = candidate
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
        if self.called_numbers is None:
            self.called_numbers = []

    def save(self, *args, **kwargs):
        self._ensure_game_code()
        self._ensure_draws()
        super().save(*args, **kwargs)


class ShopBingoSession(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting"
        LOCKED = "locked", "Locked"
        CANCELLED = "cancelled", "Cancelled"

    shop = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="shop_bingo_sessions", on_delete=models.CASCADE)
    session_id = models.CharField(max_length=24, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.WAITING)
    fixed_players = models.PositiveSmallIntegerField(default=4)
    min_bet_per_cartella = models.DecimalField(max_digits=12, decimal_places=2, default=20)
    players_data = models.JSONField(default=list, blank=True)
    locked_cartellas = models.JSONField(default=list, blank=True)
    total_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    game = models.OneToOneField(Game, null=True, blank=True, related_name="shop_session", on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.session_id} ({self.shop.username})"

    def _ensure_session_id(self):
        if self.session_id:
            return
        candidate = f"SHOP-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"
        while type(self).objects.filter(session_id=candidate).exists():
            candidate = f"SHOP-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"
        self.session_id = candidate

    def save(self, *args, **kwargs):
        self._ensure_session_id()
        super().save(*args, **kwargs)
