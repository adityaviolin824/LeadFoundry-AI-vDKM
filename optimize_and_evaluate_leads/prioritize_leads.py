def sort_leads(leads: list[dict]) -> list[dict]:
    def rank(lead: dict) -> int:
        # 1. Safely handle None, missing keys, and whitespace
        # "or ''" converts None to empty string before stripping
        mail = str(lead.get("mail") or "").strip().lower()
        phone = str(lead.get("phone_number") or "").strip().lower()

        # 2. Define what counts as "empty" (expand this list if needed)
        invalid_values = ("unknown", "", "none", "n/a")

        has_mail = mail not in invalid_values
        has_phone = phone not in invalid_values

        # 3. Priority Logic
        if has_mail and has_phone:
            return 0   # Highest: Contactable via both
        if has_mail:
            return 1   # High: Email is usually preferred over phone
        if has_phone:
            return 2   # Medium: Phone only
        return 3       # Lowest: No contact info

    return sorted(leads, key=rank)