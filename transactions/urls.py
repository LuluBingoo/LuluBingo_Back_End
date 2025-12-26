from django.urls import path

from .views import DepositView, TransactionListView, WithdrawView

urlpatterns = [
    path("transactions/deposit", DepositView.as_view(), name="tx-deposit"),
    path("transactions/withdraw", WithdrawView.as_view(), name="tx-withdraw"),
    path("transactions/history", TransactionListView.as_view(), name="tx-history"),
]
