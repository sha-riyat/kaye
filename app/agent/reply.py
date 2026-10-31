"""What Kayé says back: plain data, so the same logic drives WhatsApp, tests and the replay script."""

from dataclasses import dataclass, field


@dataclass
class Reply:
    text: str = ""
    buttons: list[tuple[str, str]] = field(default_factory=list)  # (id, title <= 20 chars), at most 3
    rows: list[tuple[str, str, str]] = field(default_factory=list)  # list message: (id, title, description)
    list_button: str = "Choisir"
    image: bytes | None = None  # PNG, sent as an image with `text` as caption
    link: str | None = None  # wa.me link appended to the text by the sender
    kind: str = "info"  # proposal (waits for Oui), question (missing value), choice (pick a contact), info

    def __post_init__(self) -> None:
        if len(self.buttons) > 3:
            raise ValueError("WhatsApp allows at most 3 reply buttons")
        if any(len(title) > 20 for _, title in self.buttons):
            raise ValueError("button titles are limited to 20 characters")


def confirm_buttons(pending_id: int) -> list[tuple[str, str]]:
    return [
        (f"ok:{pending_id}", "Oui, noter"),
        (f"fix:{pending_id}", "Corriger"),
        (f"no:{pending_id}", "Annuler"),
    ]
