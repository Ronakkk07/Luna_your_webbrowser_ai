from rest_framework import serializers
from .models import ShoppingItem

class ShoppingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShoppingItem
        fields = "__all__"
        read_only_fields = ["user", "created_at"]