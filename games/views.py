from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Game
from .serializers import GameCompleteSerializer, GameCreateSerializer, GameSerializer


class GameListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: GameSerializer(many=True)}, tags=["Games"])
    def get(self, request):
        games = Game.objects.filter(shop=request.user)
        return Response(GameSerializer(games, many=True).data)

    @extend_schema(request=GameCreateSerializer, responses={201: GameSerializer}, tags=["Games"])
    def post(self, request):
        serializer = GameCreateSerializer(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        game = serializer.save()
        return Response(GameSerializer(game).data, status=status.HTTP_201_CREATED)


class GameDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_game(self, code, user):
        return get_object_or_404(Game, game_code=code, shop=user)

    @extend_schema(responses={200: GameSerializer, 404: OpenApiResponse(description="Not found")}, tags=["Games"])
    def get(self, request, code: str):
        game = self._get_game(code, request.user)
        return Response(GameSerializer(game).data)


class GameDrawView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: GameSerializer}, tags=["Games"])
    def get(self, request, code: str):
        game = get_object_or_404(Game, game_code=code, shop=request.user)
        data = {
            "game_code": game.game_code,
            "draw_sequence": game.draw_sequence,
            "cartella_draw_sequences": game.cartella_draw_sequences,
        }
        return Response(data)


class GameCartellaDrawView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        responses={200: OpenApiResponse(description="Cartella draw sequence returned")},
        tags=["Games"],
        summary="Public cartella draw",
    )
    def get(self, request, code: str, cartella_number: int):
        game = get_object_or_404(Game, game_code=code)
        cartella_index = cartella_number - 1
        if cartella_index < 0 or cartella_index >= len(game.cartella_draw_sequences):
            return Response({"detail": "Cartella not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "game_code": game.game_code,
                "cartella_number": cartella_number,
                "cartella_numbers": game.cartella_numbers[cartella_index],
                "cartella_draw_sequence": game.cartella_draw_sequences[cartella_index],
            }
        )


class GameCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=GameCompleteSerializer, responses={200: GameSerializer}, tags=["Games"])
    def post(self, request, code: str):
        game = get_object_or_404(Game, game_code=code, shop=request.user)
        serializer = GameCompleteSerializer(game, data=request.data)
        serializer.is_valid(raise_exception=True)
        game = serializer.save()
        return Response(GameSerializer(game).data)
