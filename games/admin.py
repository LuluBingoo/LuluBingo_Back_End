from django.contrib import admin
from django.utils import timezone

from .models import Game


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "game_code",
        "shop",
        "status",
        "bet_amount",
        "num_players",
        "win_amount",
        "cartella_count",
        "created_at",
        "started_at",
        "ended_at",
    )
    list_filter = ("status", "created_at", "started_at", "ended_at")
    search_fields = ("game_code", "shop__username", "shop__shop_code")
    list_select_related = ("shop",)
    readonly_fields = (
        "game_code",
        "draw_sequence",
        "cartella_draw_sequences",
        "created_at",
        "started_at",
        "ended_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    fieldsets = (
        ("Game", {"fields": ("shop", "game_code", "status")}),
        (
            "Stakes",
            {
                "fields": (
                    "bet_amount",
                    "num_players",
                    "win_amount",
                )
            },
        ),
        (
            "Cartellas & Draws",
            {
                "classes": ("collapse",),
                "fields": (
                    "cartella_numbers",
                    "cartella_draw_sequences",
                    "draw_sequence",
                ),
            },
        ),
        (
            "Timeline",
            {
                "fields": (
                    "created_at",
                    "started_at",
                    "ended_at",
                )
            },
        ),
        (
            "Result",
            {
                "fields": (
                    "winners",
                )
            },
        ),
    )

    actions = ["mark_active", "mark_completed", "mark_cancelled"]

    @admin.display(description="Cartellas")
    def cartella_count(self, obj: Game) -> int:
        return len(obj.cartella_numbers or [])

    def mark_active(self, request, queryset):
        updated = 0
        for game in queryset:
            if game.status != Game.Status.ACTIVE:
                game.status = Game.Status.ACTIVE
                game.started_at = game.started_at or timezone.now()
                game.save(update_fields=["status", "started_at"])
                updated += 1
        self.message_user(request, f"Marked {updated} game(s) active.")

    mark_active.short_description = "Mark selected games as active"

    def mark_completed(self, request, queryset):
        updated = 0
        for game in queryset:
            if game.status != Game.Status.COMPLETED:
                game.status = Game.Status.COMPLETED
                game.ended_at = timezone.now()
                game.save(update_fields=["status", "ended_at"])
                updated += 1
        self.message_user(request, f"Marked {updated} game(s) completed.")

    mark_completed.short_description = "Mark selected games as completed"

    def mark_cancelled(self, request, queryset):
        updated = 0
        for game in queryset:
            if game.status != Game.Status.CANCELLED:
                game.status = Game.Status.CANCELLED
                game.ended_at = timezone.now()
                game.save(update_fields=["status", "ended_at"])
                updated += 1
        self.message_user(request, f"Cancelled {updated} game(s).")

    mark_cancelled.short_description = "Cancel selected games"
