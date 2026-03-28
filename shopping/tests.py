from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from requests import RequestException
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ShoppingItem
from .services import CityInfoLookupError, fetch_city_info
from .tasks import add_shopping_items_task


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_STORE_EAGER_RESULT=True,
)
class ShoppingTaskTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="shopping-user",
            password="StrongPassword123",
        )

    def test_add_shopping_items_task_creates_unique_items(self):
        result = add_shopping_items_task.delay(
            self.user.id,
            ["Milk", "milk", "Eggs", "  "],
        )

        self.assertEqual(result.get(), ["Milk", "Eggs"])
        self.assertEqual(ShoppingItem.objects.filter(user=self.user).count(), 2)


class CityInfoServiceTests(TestCase):
    @override_settings(CITY_INFO_API_URL="https://example.com/city-info")
    @patch("shopping.services.requests.get")
    def test_fetch_city_info_returns_json_payload(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "city": "Dublin",
            "country": "Ireland",
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        data = fetch_city_info(" Dublin ")

        self.assertEqual(data["city"], "Dublin")
        mock_get.assert_called_once_with(
            "https://example.com/city-info?city=Dublin",
            timeout=10,
        )

    def test_fetch_city_info_requires_city(self):
        with self.assertRaisesMessage(ValueError, "City is required."):
            fetch_city_info("   ")

    @patch("shopping.services.requests.get")
    def test_fetch_city_info_raises_when_json_is_invalid(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("bad json")
        mock_get.return_value = mock_response

        with self.assertRaisesMessage(
            CityInfoLookupError,
            "City info service returned invalid JSON.",
        ):
            fetch_city_info("Dublin")


class CityInfoEndpointTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="city-user",
            password="StrongPassword123",
        )
        self.client.force_authenticate(user=self.user)

    @patch("shopping.views.fetch_city_info")
    def test_city_info_endpoint_returns_city_payload(self, mock_fetch_city_info):
        mock_fetch_city_info.return_value = {
            "city": "Dublin",
            "country": "Ireland",
            "country_code": "IE",
        }

        response = self.client.get("/api/shopping/city-info/?city=Dublin")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["city"], "Dublin")
        self.assertEqual(response.data["country"], "Ireland")
        mock_fetch_city_info.assert_called_once_with("Dublin")

    def test_city_info_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/shopping/city-info/?city=Dublin")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("shopping.views.fetch_city_info", side_effect=ValueError("City is required."))
    def test_city_info_endpoint_returns_400_for_missing_city(self, mock_fetch_city_info):
        response = self.client.get("/api/shopping/city-info/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {"error": "City is required."})
        mock_fetch_city_info.assert_called_once_with(None)

    @patch("shopping.views.fetch_city_info", side_effect=RequestException("boom"))
    def test_city_info_endpoint_returns_502_when_service_is_unavailable(
        self,
        mock_fetch_city_info,
    ):
        response = self.client.get("/api/shopping/city-info/?city=Dublin")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(
            response.data,
            {"error": "City info service is unavailable right now."},
        )
        mock_fetch_city_info.assert_called_once_with("Dublin")
