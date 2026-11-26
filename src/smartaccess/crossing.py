from dataclasses import dataclass


@dataclass(frozen=True)
class CountingLine:
    y: float = 0.55
    tolerance: float = 0.03
    entry_down: bool = True

    def __post_init__(self):
        if not 0 < self.tolerance < min(self.y, 1 - self.y):
            raise ValueError("La ligne et sa zone de tolérance doivent tenir dans l’image.")

    def side(self, y: float) -> int:
        if y < self.y - self.tolerance:
            return -1
        if y > self.y + self.tolerance:
            return 1
        return 0


class CrossingCounter:
    def __init__(self, line: CountingLine, max_gap: int = 30):
        self.line = line
        self.max_gap = max_gap
        self.tracks: dict[int, tuple[int, int]] = {}

    def observe(self, frame_number: int, positions: dict[int, float]) -> list[tuple[int, str]]:
        self.tracks = {
            track_id: state for track_id, state in self.tracks.items()
            if frame_number - state[1] <= self.max_gap
        }
        passages = []
        for track_id, y in positions.items():
            current = self.line.side(y)
            previous, _ = self.tracks.get(track_id, (0, frame_number))
            if current and previous and current != previous:
                direction = "entry" if (current > previous) == self.line.entry_down else "exit"
                passages.append((track_id, direction))
            self.tracks[track_id] = (current or previous, frame_number)
        return passages
