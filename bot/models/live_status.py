from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class LiveStatusState:
    volume_db: float
    muted: bool
    track_title: str
    track_active: bool
