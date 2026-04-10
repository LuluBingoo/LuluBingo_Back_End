from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from games.models import Game
from transactions.models import Transaction
from transactions.serializers import TransactionSerializer

from .admin_serializers import (
    AdminGameListSerializer,
    AdminShopCreateSerializer,
    AdminShopUpdateSerializer,
    AdminTransactionListSerializer,
    ManagerCreateSerializer,
    ManagerUpdateSerializer,
)
from .models import ShopUser
from .serializers import ShopUserSerializer


class IsManagerPermission(permissions.BasePermission):
    message = "Manager access is required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return bool(
            user.status == ShopUser.Status.ACTIVE
            and user.role == ShopUser.Role.MANAGER
            and user.is_staff
        )


def _parse_limit(request, default: int = 200, max_value: int = 1000) -> int:
    raw = (request.query_params.get("limit") or "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(1, min(parsed, max_value))


class AdminManagerListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsManagerPermission]

    @extend_schema(
        parameters=[
            OpenApiParameter(name="search", required=False, type=str),
            OpenApiParameter(name="limit", required=False, type=int),
        ],
        responses={200: ShopUserSerializer(many=True)},
        tags=["Admin"],
    )
    def get(self, request):
        search = (request.query_params.get("search") or "").strip()
        managers = ShopUser.objects.filter(role=ShopUser.Role.MANAGER).order_by("-created_at")

        if search:
            managers = managers.filter(
                Q(username__icontains=search)
                | Q(name__icontains=search)
                | Q(contact_email__icontains=search)
                | Q(contact_phone__icontains=search)
            )

        limit = _parse_limit(request)
        return Response(ShopUserSerializer(managers[:limit], many=True).data)

    @extend_schema(
        request=ManagerCreateSerializer,
        responses={201: ShopUserSerializer},
        tags=["Admin"],
    )
    def post(self, request):
        serializer = ManagerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        manager = serializer.save()
        return Response(ShopUserSerializer(manager).data, status=status.HTTP_201_CREATED)


class AdminManagerDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsManagerPermission]

    def _get_manager(self, user_id: int) -> ShopUser:
        return get_object_or_404(ShopUser, pk=user_id, role=ShopUser.Role.MANAGER)

    @extend_schema(responses={200: ShopUserSerializer}, tags=["Admin"])
    def get(self, request, user_id: int):
        manager = self._get_manager(user_id)
        return Response(ShopUserSerializer(manager).data)

    @extend_schema(
        request=ManagerUpdateSerializer,
        responses={200: ShopUserSerializer},
        tags=["Admin"],
    )
    def patch(self, request, user_id: int):
        manager = self._get_manager(user_id)
        serializer = ManagerUpdateSerializer(instance=manager, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        manager = serializer.save()
        return Response(ShopUserSerializer(manager).data)

    @extend_schema(
        request=None,
        responses={
            204: OpenApiResponse(description="Manager deleted"),
            400: OpenApiResponse(description="Cannot delete yourself or the last active manager"),
        },
        tags=["Admin"],
    )
    def delete(self, request, user_id: int):
        manager = self._get_manager(user_id)

        if manager.pk == request.user.pk:
            return Response(
                {"detail": "You cannot delete your own manager account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        active_managers = ShopUser.objects.filter(
            role=ShopUser.Role.MANAGER,
            status=ShopUser.Status.ACTIVE,
        ).count()
        if manager.status == ShopUser.Status.ACTIVE and active_managers <= 1:
            return Response(
                {"detail": "At least one active manager must remain."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        manager.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminShopListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsManagerPermission]

    @extend_schema(
        parameters=[
            OpenApiParameter(name="search", required=False, type=str),
            OpenApiParameter(name="status", required=False, type=str),
            OpenApiParameter(name="limit", required=False, type=int),
        ],
        responses={200: ShopUserSerializer(many=True)},
        tags=["Admin"],
    )
    def get(self, request):
        search = (request.query_params.get("search") or "").strip()
        status_filter = (request.query_params.get("status") or "").strip().lower()

        shops = ShopUser.objects.filter(role=ShopUser.Role.SHOP).order_by("-created_at")

        if status_filter:
            shops = shops.filter(status=status_filter)

        if search:
            shops = shops.filter(
                Q(username__icontains=search)
                | Q(name__icontains=search)
                | Q(contact_email__icontains=search)
                | Q(contact_phone__icontains=search)
                | Q(shop_code__icontains=search)
                | Q(human_shop_id__icontains=search)
            )

        limit = _parse_limit(request)
        return Response(ShopUserSerializer(shops[:limit], many=True).data)

    @extend_schema(
        request=AdminShopCreateSerializer,
        responses={201: OpenApiResponse(description="Shop and initial funding transaction created")},
        tags=["Admin"],
    )
    def post(self, request):
        serializer = AdminShopCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        shop = serializer.save()
        initial_tx = getattr(shop, "_initial_funding_tx", None)

        payload = {"shop": ShopUserSerializer(shop).data}
        if initial_tx is not None:
            payload["initial_transaction"] = TransactionSerializer(initial_tx).data

        return Response(payload, status=status.HTTP_201_CREATED)


class AdminShopDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsManagerPermission]

    def _get_shop(self, user_id: int) -> ShopUser:
        return get_object_or_404(ShopUser, pk=user_id, role=ShopUser.Role.SHOP)

    @extend_schema(responses={200: ShopUserSerializer}, tags=["Admin"])
    def get(self, request, user_id: int):
        shop = self._get_shop(user_id)
        return Response(ShopUserSerializer(shop).data)

    @extend_schema(
        request=AdminShopUpdateSerializer,
        responses={200: ShopUserSerializer},
        tags=["Admin"],
    )
    def patch(self, request, user_id: int):
        shop = self._get_shop(user_id)
        serializer = AdminShopUpdateSerializer(instance=shop, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        shop = serializer.save()
        return Response(ShopUserSerializer(shop).data)

    @extend_schema(
        request=None,
        responses={204: OpenApiResponse(description="Shop deleted")},
        tags=["Admin"],
    )
    def delete(self, request, user_id: int):
        shop = self._get_shop(user_id)
        shop.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminGameListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsManagerPermission]

    @extend_schema(
        parameters=[
            OpenApiParameter(name="shop_id", required=False, type=int),
            OpenApiParameter(name="status", required=False, type=str),
            OpenApiParameter(name="game_code", required=False, type=str),
            OpenApiParameter(name="limit", required=False, type=int),
        ],
        responses={200: AdminGameListSerializer(many=True)},
        tags=["Admin"],
    )
    def get(self, request):
        shop_id_raw = (request.query_params.get("shop_id") or "").strip()
        status_filter = (request.query_params.get("status") or "").strip().lower()
        game_code = (request.query_params.get("game_code") or "").strip()

        games = Game.objects.select_related("shop").all().order_by("-created_at")
        if shop_id_raw:
            try:
                games = games.filter(shop_id=int(shop_id_raw))
            except ValueError:
                return Response({"detail": "shop_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        if status_filter:
            games = games.filter(status=status_filter)

        if game_code:
            games = games.filter(game_code__icontains=game_code)

        limit = _parse_limit(request)
        return Response(AdminGameListSerializer(games[:limit], many=True).data)


class AdminTransactionListView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsManagerPermission]

    @extend_schema(
        parameters=[
            OpenApiParameter(name="shop_id", required=False, type=int),
            OpenApiParameter(name="tx_type", required=False, type=str),
            OpenApiParameter(name="search", required=False, type=str),
            OpenApiParameter(name="limit", required=False, type=int),
        ],
        responses={200: AdminTransactionListSerializer(many=True)},
        tags=["Admin"],
    )
    def get(self, request):
        shop_id_raw = (request.query_params.get("shop_id") or "").strip()
        tx_type = (request.query_params.get("tx_type") or "").strip().lower()
        search = (request.query_params.get("search") or "").strip()

        transactions = Transaction.objects.select_related("user").all().order_by("-created_at")
        if shop_id_raw:
            try:
                transactions = transactions.filter(user_id=int(shop_id_raw))
            except ValueError:
                return Response({"detail": "shop_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        if tx_type:
            transactions = transactions.filter(tx_type=tx_type)

        if search:
            transactions = transactions.filter(
                Q(reference__icontains=search)
                | Q(user__username__icontains=search)
                | Q(user__name__icontains=search)
            )

        limit = _parse_limit(request)
        return Response(AdminTransactionListSerializer(transactions[:limit], many=True).data)
