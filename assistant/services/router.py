from reminders.models import Reminder
from shopping.models import ShoppingItem
from django.utils import timezone
from dateutil.parser import parse as parse_datetime

def route_intent(data, user):
    intent = data.get("intent")
    task = (data.get("task") or "").lower()
    transcript = data.get("task")  # raw transcript if needed

    # ------------------- CREATE REMINDER -------------------
    if intent == "create_reminder":
        task_name = data.get("task")
        dt_str = data.get("datetime")
        if dt_str:
            try:
                dt = parse_datetime(dt_str)
            except:
                dt = timezone.now()
        else:
            dt = timezone.now()
        reminder = Reminder.objects.create(user=user, task=task_name, date_time=dt)
        return f"Reminder created: {reminder.task} at {reminder.date_time.strftime('%Y-%m-%d %H:%M')}"

    # ------------------- ADD SHOPPING ITEMS -------------------
    if intent == "add_shopping":
        items = data.get("items", [])
        added_items = []
        for item in items:
            if not ShoppingItem.objects.filter(user=user, item_name__iexact=item).exists():
                ShoppingItem.objects.create(user=user, item_name=item, quantity=1)
                added_items.append(item)
        if added_items:
            return f"Items added to shopping list: {', '.join(added_items)}"
        return "No new items added (already in list)."

    # ------------------- LIST / SUMMARIZE SHOPPING -------------------
    if intent in ["summarize", "list_shopping"] and "shopping" in task:
        items = user.shopping_items.all()
        if items.exists():
            return "Your shopping list: " + ", ".join([f"{i.item_name} ({i.quantity})" for i in items])
        return "Your shopping list is empty."

    # ------------------- LIST / SUMMARIZE REMINDERS -------------------
    if intent in ["summarize", "list_reminders"] and "reminder" in task:
        reminders = user.reminders.all()
        if reminders.exists():
            return "Your reminders: " + ", ".join([f"{r.task} at {r.date_time.strftime('%Y-%m-%d %H:%M')}" for r in reminders])
        return "You have no reminders."

    # ------------------- CASUAL CHAT -------------------
    if intent == "unknown":
        return small_chatbot_response(transcript)  # implement a simple Gemini prompt for chit-chat

    return "Sorry, I didn't understand that command."