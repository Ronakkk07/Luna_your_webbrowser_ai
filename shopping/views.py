import requests
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import ShoppingItem
from .serializers import ShoppingItemSerializer
from .services import CityInfoLookupError, fetch_city_info

class ShoppingViewSet(viewsets.ModelViewSet):
    serializer_class = ShoppingItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ShoppingItem.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["get"], url_path="city-info")
    def city_info(self, request):
        city = request.query_params.get("city")

        try:
            city_info = fetch_city_info(city)
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except requests.RequestException:
            return Response(
                {"error": "City info service is unavailable right now."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except CityInfoLookupError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(city_info)
