def sort_leads(leads: list[dict]) -> list[dict]:
    def rank(lead: dict) -> int:
        mail = str(lead.get("mail") or "").strip().lower()
        phone = str(lead.get("phone_number") or "").strip().lower()

        invalid_values = ("unknown", "", "none", "n/a")

        has_mail = mail not in invalid_values
        has_phone = phone not in invalid_values

        if has_mail and has_phone:
            return 0
        if has_mail:
            return 1
        if has_phone:
            return 2
        return 3

    return sorted(leads, key=rank)
