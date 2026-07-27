class PreferenceParser:
    def normalize(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            item = value.strip().lower()
            if item and item not in seen:
                seen.add(item)
                normalized.append(item)
        return normalized
