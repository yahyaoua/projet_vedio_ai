import pytest

from src.smartaccess.crossing import CountingLine, CrossingCounter


@pytest.mark.parametrize(("trajectory", "expected"), [
    ([0.30, 0.47, 0.51, 0.65, 0.75], ["entry"]),
    ([0.75, 0.53, 0.49, 0.30], ["exit"]),
    ([0.25, 0.35, 0.47, 0.40], []),
    ([0.30, 0.46, 0.54, 0.48, 0.52, 0.48, 0.30], []),
    ([0.30, 0.70, 0.51, 0.49, 0.70, 0.51, 0.30], ["entry", "exit"]),
    ([0.50, 0.53, 0.70], []),
])
def test_crossings(trajectory, expected):
    counter = CrossingCounter(CountingLine(y=0.5, tolerance=0.05))
    events = [
        event
        for frame, y in enumerate(trajectory, start=1)
        for event in counter.observe(frame, {42: y})
    ]
    assert events == [(42, direction) for direction in expected]


def test_entry_direction_can_be_inverted():
    counter = CrossingCounter(CountingLine(entry_down=False))
    assert counter.observe(1, {42: 0.25}) == []
    assert counter.observe(2, {42: 0.75}) == [(42, "exit")]
    assert counter.observe(3, {42: 0.25}) == [(42, "entry")]


def test_tracks_are_independent_and_long_gaps_reset_history():
    counter = CrossingCounter(CountingLine(), max_gap=3)
    assert counter.observe(1, {1: 0.25, 2: 0.75}) == []
    assert counter.observe(2, {2: 0.25}) == [(2, "exit")]
    assert counter.observe(5, {1: 0.75}) == []
