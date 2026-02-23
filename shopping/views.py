from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import ShoppingItem
from .serializers import ShoppingItemSerializer

class ShoppingViewSet(viewsets.ModelViewSet):
    serializer_class = ShoppingItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ShoppingItem.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)