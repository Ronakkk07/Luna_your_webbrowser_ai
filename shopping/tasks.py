from celery import shared_task
from django.contrib.auth import get_user_model

from .models import ShoppingItem


def add_shopping_items_for_user(user, items):
    added_items = []

    for raw_item in items:
        item_name = (raw_item or "").strip()
        if not item_name:
            continue

        exists = ShoppingItem.objects.filter(
            user=user,
            item_name__iexact=item_name,
        ).exists()
        if exists:
            continue

        ShoppingItem.objects.create(user=user, item_name=item_name, quantity=1)
        added_items.append(item_name)

    return added_items


@shared_task
def add_shopping_items_task(user_id, items):
    user = get_user_model().objects.get(pk=user_id)
    return add_shopping_items_for_user(user, items)
