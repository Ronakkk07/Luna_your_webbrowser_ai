from reminders.models import Reminder
from shopping.models import ShoppingItem
from django.utils import timezone
from datetime import datetime


def route_intent(data, user):

    intent = data.get("intent")

    if intent == "create_reminder":
        reminder = Reminder.objects.create(
            user=user,
            task=data.get("task"),
            date_time=timezone.now()  # improve later
        )
        return f"Reminder created: {reminder.task}"

    if intent == "add_shopping":
        items = data.get("items", [])
        for item in items:
            ShoppingItem.objects.create(
                user=user,
                item_name=item,
                quantity=1
            )
        return "Items added to shopping list."

    if intent == "summarize":
        return data.get("task")

    return "Sorry, I didn't understand that command."