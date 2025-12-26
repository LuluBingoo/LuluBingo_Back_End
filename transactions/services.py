from decimal import Decimal
from typing import Optional

from django.db import transaction as db_transaction

from accounts.models import ShopUser
from .models import Transaction


class TransactionError(Exception):
    pass


CREDIT_TYPES = {Transaction.Type.DEPOSIT, Transaction.Type.BET_CREDIT, Transaction.Type.ADJUSTMENT}
DEBIT_TYPES = {Transaction.Type.WITHDRAWAL, Transaction.Type.BET_DEBIT}
ALL_TYPES = CREDIT_TYPES | DEBIT_TYPES


def apply_transaction(
    user: ShopUser,
    amount: Decimal,
    tx_type: str,
    reference: str = "",
    metadata: Optional[dict] = None,
) -> Transaction:
    metadata = metadata or {}
    amount = Decimal(amount)
    if amount <= 0:
        raise TransactionError("Amount must be positive")
    if tx_type not in ALL_TYPES:
        raise TransactionError("Unknown transaction type")

    delta = amount if tx_type in CREDIT_TYPES else -amount

    with db_transaction.atomic():
        locked_user = ShopUser.objects.select_for_update().get(pk=user.pk)
        before = locked_user.wallet_balance
        after = before + delta
        if after < 0:
            raise TransactionError("Insufficient balance")
        locked_user.wallet_balance = after
        locked_user.save(update_fields=["wallet_balance"])

        tx = Transaction.objects.create(
            user=locked_user,
            tx_type=tx_type,
            amount=amount,
            balance_before=before,
            balance_after=after,
            reference=reference,
            metadata=metadata,
        )
    return tx
