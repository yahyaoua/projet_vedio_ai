import sys
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np

from src.smartaccess import counting, database
from src.smartaccess.config import Settings
from src.smartaccess.crossing import CountingLine


def test_annotation_draws_boxes_without_using_untracked_detections_for_counts(monkeypatch):
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    box = SimpleNamespace(cpu=lambda: np.array([[15, 12, 25, 30]]))
    arrows = {}

    def record_arrow(frame, start, end, *args, **kwargs):
        arrows[start[0]] = end[1] > start[1]

    monkeypatch.setattr(counting.cv2, "arrowedLine", record_arrow)
    assert counting.annotate(frame, SimpleNamespace(xyxy=box, id=None), CountingLine(entry_down=False)) == {}
    assert frame[12, 15].any()
    assert frame[round(0.55 * 119), -1].any()
    assert [arrows[x] for x in sorted(arrows)] == [False, True]


def test_processing_reuses_one_model_and_persists_separate_sessions(tmp_path, monkeypatch):
    settings = Settings(database=tmp_path / "test.sqlite3", models=tmp_path)
    database.initialize(settings.database)
    (tmp_path / "yolo11n.pt").touch()
    model_loads = []
    tracked = []
    released = []

    def track(frame, **kwargs):
        tracked.append((kwargs["classes"], kwargs["tracker"], kwargs["persist"]))
        return [SimpleNamespace(boxes={7: frame.item()})]

    def load_model(path, task):
        model_loads.append((path, task))
        return SimpleNamespace(names={0: "person"}, track=track)

    @contextmanager
    def capture(path):
        try:
            yield [np.array(y) for y in (0.25, 0.55, 0.75, 0.25)]
        finally:
            released.append(path)

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=load_model))
    monkeypatch.setattr(counting, "open_capture", capture)
    monkeypatch.setattr(counting, "frames", iter)
    monkeypatch.setattr(counting, "annotate", lambda frame, boxes, line: boxes)

    runs = [counting.CountingRun(settings, CountingLine()) for _ in range(2)]
    for run in runs:
        run._run()
        result = run.snapshot()
        assert (result.status, result.entries, result.exits, result.frames) == ("done", 1, 1, 4)
        assert result.fps > 0

    assert runs[0].session_id != runs[1].session_id
    assert len(model_loads) == len(released) == 2
    assert tracked == [([0], "bytetrack.yaml", True)] * 8
    with database.connection(settings.database) as db:
        assert db.execute("""
            SELECT session_id, track_id, direction FROM passage_events ORDER BY id
        """).fetchall() == [
            (run.session_id, 7, direction) for run in runs for direction in ("entry", "exit")
        ]
