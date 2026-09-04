from app.modules.explorer.public import ExplorerOutput


def compose_source_summary(output: ExplorerOutput) -> str:
    if output.status == "error":
        return (
            output.error.message
            if output.error is not None
            else "Explorer không thể đọc nguồn này."
        )

    parts: list[str] = []
    if output.input_adm:
        parts.append(f"Nguồn nói về {output.input_adm}.")
    places = [place.name for place in (output.places or [])]
    if places:
        parts.append("Các địa điểm được nhắc đến: " + ", ".join(places[:12]) + ".")
    notes = list(dict.fromkeys(note.summary for note in (output.url_notes or [])))
    if notes:
        parts.append(" ".join(notes[:6]))
    if not parts:
        return "Penguin đã đọc nguồn nhưng chưa trích xuất được nội dung đủ rõ để tóm tắt."
    return "\n\n".join(parts)
