from django.urls import path

from .views import (
    GameCartellaDrawView,
    GameClaimView,
    GameCompleteView,
    GameDetailView,
    GameDrawView,
    GameListCreateView,
    PublicGameCartellaView,
    ShopBingoSessionConfirmPaymentView,
    ShopBingoSessionCreateView,
    ShopBingoSessionDetailView,
    ShopBingoSessionReserveView,
)

urlpatterns = [
    path("games", GameListCreateView.as_view(), name="games"),
    path("games/shop-mode/sessions", ShopBingoSessionCreateView.as_view(), name="shop-mode-session-create"),
    path("games/shop-mode/sessions/<str:session_id>", ShopBingoSessionDetailView.as_view(), name="shop-mode-session-detail"),
    path("games/shop-mode/sessions/<str:session_id>/reserve", ShopBingoSessionReserveView.as_view(), name="shop-mode-session-reserve"),
    path("games/shop-mode/sessions/<str:session_id>/confirm-payment", ShopBingoSessionConfirmPaymentView.as_view(), name="shop-mode-session-confirm"),
    path("games/<str:code>", GameDetailView.as_view(), name="game-detail"),
    path("games/<str:code>/draw", GameDrawView.as_view(), name="game-draw"),
    path("games/<str:code>/cartellas/<int:cartella_number>/draw", GameCartellaDrawView.as_view(), name="game-cartella-draw"),
    path("games/<str:code>/claim", GameClaimView.as_view(), name="game-claim"),
    path("games/<str:code>/complete", GameCompleteView.as_view(), name="game-complete"),
    path("game/<str:game_id>/cartella/<int:cartella_number>", PublicGameCartellaView.as_view(), name="public-game-cartella"),
]
