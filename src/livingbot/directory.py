import re


class Directory:
    """Two-way map between Discord user ids and the display names people go by.

    The model only ever sees names. Ids are resolved back on the way out, so
    nothing depends on the model copying an 18-digit number correctly.
    """

    def __init__(self, names: dict[str, str]) -> None:
        self._names = names
        # Longest first, so "@Jack Black" is not matched as "@Jack" when both exist.
        self._by_length = sorted(
            names.items(), key=lambda item: len(item[1]), reverse=True
        )

    def name_for(self, user_id: str) -> str:
        return self._names.get(user_id, f"User {user_id}")

    def id_for(self, name: str) -> str | None:
        target = name.strip().lstrip("@").casefold()
        for user_id, display_name in self._by_length:
            if display_name.casefold() == target:
                return user_id
        return None

    def to_mentions(self, text: str) -> str:
        """Turn the '@Name' the model writes into a mention Discord will ping."""
        for user_id, display_name in self._by_length:
            text = re.sub(rf"@{re.escape(display_name)}(?!\w)", f"<@{user_id}>", text)
        return text
