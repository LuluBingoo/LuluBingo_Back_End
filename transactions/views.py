from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Transaction
from .serializers import AmountSerializer, TransactionSerializer
from .services import TransactionError, apply_transaction


class DepositView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=AmountSerializer, responses={201: TransactionSerializer}, tags=["Transactions"])
    def post(self, request):
        serializer = AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tx = apply_transaction(
            user=request.user,
            amount=serializer.validated_data["amount"],
            tx_type=Transaction.Type.DEPOSIT,
            reference=serializer.validated_data.get("reference", ""),
        )
        return Response(TransactionSerializer(tx).data, status=status.HTTP_201_CREATED)


class WithdrawView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=AmountSerializer,
        responses={201: TransactionSerializer, 400: OpenApiResponse(description="Insufficient balance")},
        tags=["Transactions"],
    )
    def post(self, request):
        serializer = AmountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tx = apply_transaction(
                user=request.user,
                amount=serializer.validated_data["amount"],
                tx_type=Transaction.Type.WITHDRAWAL,
                reference=serializer.validated_data.get("reference", ""),
            )
        except TransactionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TransactionSerializer(tx).data, status=status.HTTP_201_CREATED)


class TransactionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: TransactionSerializer(many=True)}, tags=["Transactions"])
    def get(self, request):
        txs = Transaction.objects.filter(user=request.user).order_by("-created_at")[:200]
        return Response(TransactionSerializer(txs, many=True).data)
