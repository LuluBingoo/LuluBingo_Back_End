from django.urls import path

from .views import GameCompleteView, GameDetailView, GameDrawView, GameListCreateView

urlpatterns = [
    path("games", GameListCreateView.as_view(), name="games"),
    path("games/<str:code>", GameDetailView.as_view(), name="game-detail"),
    path("games/<str:code>/draw", GameDrawView.as_view(), name="game-draw"),
    path("games/<str:code>/complete", GameCompleteView.as_view(), name="game-complete"),
]
