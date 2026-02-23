def detect_intent(text):
    text_lower = text.lower()

    if "remind" in text_lower:
        return {"intent": "create_reminder", "text": text}

    if "add" in text_lower and "shopping" in text_lower:
        return {"intent": "add_shopping", "text": text}

    if "summarize" in text_lower:
        return {"intent": "summarize", "text": text}

    return {"intent": "unknown", "text": text}