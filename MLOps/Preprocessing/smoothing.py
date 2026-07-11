from __future__ import annotations

import math


class TimestampLowPassFilter:
    """Zero-phase low-pass filter for timestamped scalar motion signals."""

    def __init__(self, cutoff_hz: float) -> None:
        if cutoff_hz <= 0:
            raise ValueError("cutoff_hz must be positive.")
        self.cutoff_hz = cutoff_hz

    def apply(
        self,
        values: tuple[float, ...],
        timestamps_ns: tuple[int, ...],
    ) -> tuple[float, ...]:
        if len(values) != len(timestamps_ns):
            raise ValueError("Values and timestamps must have equal length.")
        if len(values) < 2:
            return values

        forward = self._filter_pass(values, timestamps_ns)
        backward = self._filter_pass(
            tuple(reversed(forward)),
            tuple(reversed(timestamps_ns)),
        )
        return tuple(reversed(backward))

    def _filter_pass(
        self,
        values: tuple[float, ...],
        timestamps_ns: tuple[int, ...],
    ) -> tuple[float, ...]:
        time_constant_s = 1.0 / (2.0 * math.pi * self.cutoff_hz)
        filtered = [values[0]]

        for index in range(1, len(values)):
            dt_s = abs(
                timestamps_ns[index] - timestamps_ns[index - 1]
            ) / 1_000_000_000
            if dt_s <= 0:
                raise ValueError("Timestamps must be strictly monotonic.")
            alpha = dt_s / (time_constant_s + dt_s)
            filtered.append(
                filtered[-1] + alpha * (values[index] - filtered[-1])
            )

        return tuple(filtered)
