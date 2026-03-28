from assistant.services.llm import small_chatbot_response
from reminders.tasks import build_reminder_datetime, create_reminder_for_user
from shopping.services import fetch_city_info
from shopping.tasks import add_shopping_items_for_user


def _format_city_info_response(city_info, requested_field=None):
    city_name = city_info.get("city") or "That city"
    field = (requested_field or "").strip().lower()

    if field == "population":
        population = city_info.get("population")
        if population is not None:
            return f"The population of {city_name} is {population:,}."
    elif field == "timezone":
        timezone = city_info.get("timezone") or {}
        timezone_name = timezone.get("name")
        offset = timezone.get("offset_string")
        if timezone_name and offset:
            return f"{city_name} is in the {timezone_name} timezone with offset {offset}."
        if timezone_name:
            return f"{city_name} is in the {timezone_name} timezone."
    elif field == "country":
        country = city_info.get("country")
        if country:
            return f"{city_name} is in {country}."
    elif field == "coordinates":
        latitude = city_info.get("latitude")
        longitude = city_info.get("longitude")
        if latitude is not None and longitude is not None:
            return f"{city_name} is located at latitude {latitude} and longitude {longitude}."
    elif field == "languages":
        languages = city_info.get("languages") or []
        if languages:
            return f"Languages spoken in {city_name} include {', '.join(languages)}."
    elif field == "currencies":
        currencies = city_info.get("currencies") or []
        if currencies:
            currency_names = [
                currency.get("name") or currency.get("code")
                for currency in currencies
                if currency.get("name") or currency.get("code")
            ]
            if currency_names:
                return f"The currency used in {city_name} is {', '.join(currency_names)}."
    elif field == "formatted_address":
        formatted_address = city_info.get("formatted_address")
        if formatted_address:
            return f"The formatted address for {city_name} is {formatted_address}."
    elif field == "country_code":
        country_code = city_info.get("country_code")
        if country_code:
            return f"The country code for {city_name} is {country_code}."

    country = city_info.get("country")
    country_code = city_info.get("country_code")
    population = city_info.get("population")
    formatted_address = city_info.get("formatted_address")
    latitude = city_info.get("latitude")
    longitude = city_info.get("longitude")
    timezone = city_info.get("timezone") or {}
    languages = city_info.get("languages") or []
    currencies = city_info.get("currencies") or []

    intro_sentence = None
    if country:
        intro_sentence = f"{city_name} is a city in {country}"
    else:
        intro_sentence = f"{city_name} is a city"

    detail_bits = []
    if country_code:
        detail_bits.append(f"country code {country_code}")
    if population is not None:
        detail_bits.append(f"a population of {population:,}")

    paragraphs = []

    if detail_bits:
        intro_sentence += ", with " + " and ".join(detail_bits)
    paragraphs.append(intro_sentence + ".")

    location_parts = []
    if formatted_address:
        location_parts.append(f"It is listed as {formatted_address}")
    if latitude is not None and longitude is not None:
        location_parts.append(f"its coordinates are {latitude}, {longitude}")
    if timezone.get("name"):
        timezone_text = f"the timezone is {timezone['name']}"
        if timezone.get("offset_string"):
            timezone_text += f" ({timezone['offset_string']})"
        location_parts.append(timezone_text)
    if location_parts:
        paragraphs.append(". ".join(location_parts) + ".")

    culture_parts = []
    if languages:
        culture_parts.append(f"Languages spoken there include {', '.join(languages)}")
    if currencies:
        currency_descriptions = []
        for currency in currencies:
            code = currency.get("code")
            name = currency.get("name")
            symbol = currency.get("symbol")
            if code and name and symbol:
                currency_descriptions.append(f"{name} ({code}, symbol {symbol})")
            elif code and name:
                currency_descriptions.append(f"{name} ({code})")
            elif name or code:
                currency_descriptions.append(name or code)
        if currency_descriptions:
            culture_parts.append(
                "The currency used is " + ", ".join(currency_descriptions)
            )
    if culture_parts:
        paragraphs.append(". ".join(culture_parts) + ".")

    if paragraphs:
        return "\n\n".join(paragraphs)

    return f"I found city information for {city_name}."


def route_intent(data, user):
    intent = data.get("intent")
    task = (data.get("task") or "").lower()
    transcript = data.get("task")

    if intent == "create_reminder":
        task_name = data.get("task") or "General reminder"
        dt = build_reminder_datetime(data.get("datetime"))
        reminder = create_reminder_for_user(user=user, task_name=task_name, dt=dt)
        return (
            f"Reminder created: {reminder.task} at "
            f"{reminder.date_time.strftime('%Y-%m-%d %H:%M')}"
        )

    if intent == "add_shopping":
        added_items = add_shopping_items_for_user(user, data.get("items", []))
        if added_items:
            return f"Items added to shopping list: {', '.join(added_items)}"
        return "No new items added (already in list)."

    if intent == "get_city_info":
        city = data.get("city")
        if not city:
            return "I couldn't tell which city you meant."

        try:
            city_info = fetch_city_info(city)
        except Exception:
            return "I couldn't fetch city information right now."

        return _format_city_info_response(city_info, data.get("city_field"))

    if intent in ["summarize", "list_shopping"] and "shopping" in task:
        items = user.shopping_items.all()
        if items.exists():
            return "Your shopping list: " + ", ".join(
                [f"{item.item_name} ({item.quantity})" for item in items]
            )
        return "Your shopping list is empty."

    if intent in ["summarize", "list_reminders"] and "reminder" in task:
        reminders = user.reminders.all()
        if reminders.exists():
            return "Your reminders: " + ", ".join(
                [
                    f"{reminder.task} at {reminder.date_time.strftime('%Y-%m-%d %H:%M')}"
                    for reminder in reminders
                ]
            )
        return "You have no reminders."

    if intent == "unknown":
        return small_chatbot_response(transcript)

    return "Sorry, I didn't understand that command."
