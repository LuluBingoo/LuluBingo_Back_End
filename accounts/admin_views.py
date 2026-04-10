import logging
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from games.models import Game
from transactions.models import Transaction
from transactions.serializers import TransactionSerializer
from transactions.services import apply_transaction

from .admin_serializers import (
    AdminGameListSerializer,
    AdminShopBalanceTopUpSerializer,
    AdminShopCreateSerializer,
    AdminShopUpdateSerializer,
    AdminTransactionListSerializer,
    ManagerCreateSerializer,
    ManagerUpdateSerializer,
)
from .emailing import send_branded_email
from .models import ShopUser
from .serializers import ShopUserSerializer


logger = logging.getLogger(__name__)


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


def _format_money(value) -> str:
    try:
        amount = Decimal(str(value))
    except Exception:
        return f"{value} ETB"
    return f"{amount:,.2f} ETB"


def _humanize_field(field_name: str) -> str:
    label = field_name.replace("_", " ").strip()
    if not label:
        return field_name
    return label.capitalize()


def _app_base_url() -> str:
    return (getattr(settings, "APP_BASE_URL", "http://localhost:5173") or "http://localhost:5173").rstrip("/")


def _send_operation_email(
    user: ShopUser,
    *,
    subject: str,
    heading: str,
    message: str,
    cta_text: str | None = None,
    cta_url: str | None = None,
    banner_text: str = "Operations Update",
) -> bool:
    if not user.contact_email:
        return False

    try:
        sent = send_branded_email(
            to_email=user.contact_email,
            subject=subject,
            heading=heading,
            message=message,
            cta_text=cta_text,
            cta_url=cta_url,
            banner_text=banner_text,
        )
        if not sent:
            logger.warning("Email was not delivered for user_id=%s subject=%s", user.id, subject)
        return sent
    except Exception as exc:
        logger.warning(
            "Failed to send operation email for user_id=%s subject=%s: %s",
            user.id,
            subject,
            exc,
        )
        return False


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

        provisioned_by = getattr(request.user, "name", "") or request.user.username
        message_lines = [
            "Welcome to Lulu Bingo administration.",
            "",
            "Your manager account is now active.",
            f"Username: {manager.username}",
            f"Status: {manager.get_status_display()}",
            f"Provisioned by: {provisioned_by}",
            "",
            "Use the password shared with you by your administrator.",
        ]
        if manager.must_change_password:
            message_lines.append("A password change is required on your next login.")

        _send_operation_email(
            manager,
            subject="Welcome to Lulu Bingo Admin",
            heading="Your manager account is ready",
            message="\n".join(message_lines),
            cta_text="Open Lulu Bingo",
            cta_url=_app_base_url(),
            banner_text="Welcome",
        )

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
        changed_fields = list(serializer.validated_data.keys())
        password_changed = "password" in changed_fields
        manager = serializer.save()

        readable_changes = [
            _humanize_field(field_name)
            for field_name in changed_fields
            if field_name != "password"
        ]

        message_lines = [
            "Your manager account settings were updated by Lulu Bingo administration.",
            f"Current status: {manager.get_status_display()}",
        ]
        if readable_changes:
            message_lines.append(f"Updated fields: {', '.join(readable_changes)}")
        if password_changed:
            message_lines.append("Your password was reset by an administrator.")
        if "must_change_password" in changed_fields and manager.must_change_password:
            message_lines.append("You must change your password on your next login.")

        _send_operation_email(
            manager,
            subject="Manager account updated",
            heading="Your manager settings changed",
            message="\n".join(message_lines),
            cta_text="Review account",
            cta_url=_app_base_url(),
            banner_text="Account Update",
        )

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

        _send_operation_email(
            manager,
            subject="Manager access removed",
            heading="Your manager access has been removed",
            message=(
                "Your manager account was removed by Lulu Bingo administration.\n"
                "If you believe this was done in error, contact support immediately."
            ),
            cta_text="Contact support",
            cta_url=_app_base_url(),
            banner_text="Access Update",
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
        requested_data = dict(serializer.validated_data)
        shop = serializer.save()
        initial_tx = getattr(shop, "_initial_funding_tx", None)

        provisioned_by = getattr(request.user, "name", "") or request.user.username
        opening_balance = requested_data.get("initial_balance", shop.wallet_balance)
        message_lines = [
            "Welcome to Lulu Bingo.",
            "",
            "Your shop account was created successfully.",
            f"Shop name: {shop.name}",
            f"Username: {shop.username}",
            f"Shop ID: {shop.human_shop_id}",
            f"Shop code: {shop.shop_code}",
            f"Opening reserve balance: {_format_money(opening_balance)}",
            f"Shop cut percentage: {shop.shop_cut_percentage}%",
            f"Lulu cut percentage: {shop.lulu_cut_percentage}%",
            f"Provisioned by: {provisioned_by}",
            "",
            "Use the password provided by your manager and keep it private.",
        ]
        if shop.must_change_password:
            message_lines.append("You must change your password on first login.")

        _send_operation_email(
            shop,
            subject="Welcome to Lulu Bingo",
            heading="Your shop account is ready",
            message="\n".join(message_lines),
            cta_text="Open Lulu Bingo",
            cta_url=_app_base_url(),
            banner_text="Welcome",
        )

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
        changed_fields = list(serializer.validated_data.keys())
        password_changed = "password" in changed_fields
        shop = serializer.save()

        readable_changes = [
            _humanize_field(field_name)
            for field_name in changed_fields
            if field_name != "password"
        ]

        message_lines = [
            "Your shop account settings were updated by Lulu Bingo administration.",
            f"Current status: {shop.get_status_display()}",
        ]
        if readable_changes:
            message_lines.append(f"Updated fields: {', '.join(readable_changes)}")
        if password_changed:
            message_lines.append("Your password was reset by an administrator.")
        if "must_change_password" in changed_fields and shop.must_change_password:
            message_lines.append("You must change your password on next login.")

        _send_operation_email(
            shop,
            subject="Shop account updated",
            heading="Your shop settings changed",
            message="\n".join(message_lines),
            cta_text="Review account",
            cta_url=_app_base_url(),
            banner_text="Account Update",
        )

        return Response(ShopUserSerializer(shop).data)

    @extend_schema(
        request=None,
        responses={204: OpenApiResponse(description="Shop deleted")},
        tags=["Admin"],
    )
    def delete(self, request, user_id: int):
        shop = self._get_shop(user_id)

        _send_operation_email(
            shop,
            subject="Shop account removed",
            heading="Your shop account has been removed",
            message=(
                "Your Lulu Bingo shop account was removed by administration.\n"
                "If this was unexpected, contact support immediately."
            ),
            cta_text="Contact support",
            cta_url=_app_base_url(),
            banner_text="Access Update",
        )

        shop.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminShopBalanceTopUpView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsManagerPermission]

    def _get_shop(self, user_id: int) -> ShopUser:
        return get_object_or_404(ShopUser, pk=user_id, role=ShopUser.Role.SHOP)

    @extend_schema(
        request=AdminShopBalanceTopUpSerializer,
        responses={
            201: OpenApiResponse(description="Shop balance topped up"),
            404: OpenApiResponse(description="Shop not found"),
        },
        tags=["Admin"],
    )
    def post(self, request, user_id: int):
        shop = self._get_shop(user_id)
        serializer = AdminShopBalanceTopUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data["amount"]
        reference = serializer.validated_data.get("reference") or f"shop:{shop.shop_code}:admin_topup"

        tx = apply_transaction(
            user=shop,
            amount=amount,
            tx_type=Transaction.Type.DEPOSIT,
            reference=reference,
            metadata={
                "event": "shop_balance_topup",
                "shop_id": shop.id,
                "shop_code": shop.shop_code,
                "shop_username": shop.username,
                "topup_by_user_id": request.user.id,
                "topup_by_username": request.user.username,
            },
            actor_role=Transaction.ActorRole.ADMIN,
            operation_source=Transaction.OperationSource.ADMIN,
        )

        shop.refresh_from_db(fields=["wallet_balance"])

        _send_operation_email(
            shop,
            subject="Reserve top-up received",
            heading="Your shop reserve balance was topped up",
            message=(
                "A reserve top-up was applied to your shop account.\n"
                f"Credited amount: {_format_money(amount)}\n"
                f"Reference: {reference}\n"
                f"Updated reserve balance: {_format_money(shop.wallet_balance)}"
            ),
            cta_text="View account",
            cta_url=_app_base_url(),
            banner_text="Balance Update",
        )

        return Response(
            {
                "shop": ShopUserSerializer(shop).data,
                "transaction": TransactionSerializer(tx).data,
            },
            status=status.HTTP_201_CREATED,
        )


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
