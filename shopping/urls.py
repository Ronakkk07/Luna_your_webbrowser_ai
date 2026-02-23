from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ShoppingViewSet

router = DefaultRouter()
router.register(r'', ShoppingViewSet, basename='shopping')

urlpatterns = [
    path('', include(router.urls)),
]