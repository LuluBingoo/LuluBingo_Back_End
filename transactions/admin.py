import csv
from typing import Iterable

from django.contrib import admin
from django.http import HttpResponse

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "tx_type",
        "amount",
        "balance_before",
        "balance_after",
        "reference",
        "created_at",
    )
    list_filter = ("tx_type", "created_at")
    search_fields = ("user__username", "user__shop_code", "reference")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("user",)
    readonly_fields = (
        "balance_before",
        "balance_after",
        "created_at",
    )
    actions = ["export_csv"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user")

    def export_csv(self, request, queryset):
        filename = "transactions.csv"
        fieldnames: Iterable[str] = (
            "id",
            "user",
            "tx_type",
            "amount",
            "balance_before",
            "balance_after",
            "reference",
            "created_at",
        )
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f"attachment; filename={filename}"

        writer = csv.writer(response)
        writer.writerow(fieldnames)
        for tx in queryset:
            writer.writerow(
                [
                    tx.id,
                    tx.user.username,
                    tx.tx_type,
                    tx.amount,
                    tx.balance_before,
                    tx.balance_after,
                    tx.reference,
                    tx.created_at.isoformat(),
                ]
            )
        return response

    export_csv.short_description = "Export selected transactions to CSV"
