from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from statistics import median

from .interpolation import IMUSampleInterpolator
from .models import IMUSample, SwingData


class SynchronizationError(ValueError):
    """Raised when the two IMU timelines cannot be synchronized."""


@dataclass(frozen=True, slots=True)
class SynchronizedFrame:
    """One timestamp containing aligned readings from both IMUs."""

    timestamp_ns: int
    forearm: IMUSample
    shoulder: IMUSample

    @property
    def timestamp_s(self) -> float:
        return self.timestamp_ns / 1_000_000_000


class IMUSynchronizer:
    """
    Aligns forearm and shoulder samples onto a shared timeline.

    Only the overlapping portion of the two recordings is used.
    No extrapolation is performed.
    """

    def __init__(
        self,
        target_sample_rate_hz: float | None = None,
        maximum_interpolation_gap_s: float = 0.02,
        interpolator: IMUSampleInterpolator | None = None,
    ) -> None:
        if target_sample_rate_hz is not None and target_sample_rate_hz <= 0:
            raise ValueError(
                "target_sample_rate_hz must be positive."
            )

        if maximum_interpolation_gap_s <= 0:
            raise ValueError(
                "maximum_interpolation_gap_s must be positive."
            )

        self.target_sample_rate_hz = target_sample_rate_hz
        self.maximum_interpolation_gap_ns = round(
            maximum_interpolation_gap_s * 1_000_000_000
        )
        self.interpolator = interpolator or IMUSampleInterpolator()

    def synchronize(
        self,
        swing: SwingData,
    ) -> tuple[SynchronizedFrame, ...]:
        """
        Produce synchronized frames from a validated swing.

        The shared timeline begins at the later sensor start time and ends
        at the earlier sensor end time.
        """
        forearm = swing.forearm_samples
        shoulder = swing.shoulder_samples

        start_ns = max(
            forearm[0].timestamp_ns,
            shoulder[0].timestamp_ns,
        )
        end_ns = min(
            forearm[-1].timestamp_ns,
            shoulder[-1].timestamp_ns,
        )

        if end_ns <= start_ns:
            raise SynchronizationError(
                "IMU 1 and IMU 2 do not have an overlapping time range."
            )

        forearm_timestamps = tuple(
            sample.timestamp_ns for sample in forearm
        )
        shoulder_timestamps = tuple(
            sample.timestamp_ns for sample in shoulder
        )
        interval_ns = (
            round(1_000_000_000 / self.target_sample_rate_hz)
            if self.target_sample_rate_hz is not None
            else self._infer_interval_ns(
                forearm_timestamps,
                shoulder_timestamps,
            )
        )

        frames: list[SynchronizedFrame] = []
        target_ns = start_ns

        while target_ns <= end_ns:
            forearm_sample = self._sample_at(
                samples=forearm,
                timestamps=forearm_timestamps,
                target_ns=target_ns,
                imu_name="IMU 1",
            )
            shoulder_sample = self._sample_at(
                samples=shoulder,
                timestamps=shoulder_timestamps,
                target_ns=target_ns,
                imu_name="IMU 2",
            )

            frames.append(
                SynchronizedFrame(
                    timestamp_ns=target_ns,
                    forearm=forearm_sample,
                    shoulder=shoulder_sample,
                )
            )

            target_ns += interval_ns

        if len(frames) < 2:
            raise SynchronizationError(
                "The overlapping recording is too short to produce "
                "at least two synchronized frames."
            )

        return tuple(frames)

    @staticmethod
    def _infer_interval_ns(
        forearm_timestamps: tuple[int, ...],
        shoulder_timestamps: tuple[int, ...],
    ) -> int:
        """Infer the native sampling interval from the supplied timestamps."""
        intervals = [
            current - previous
            for timestamps in (forearm_timestamps, shoulder_timestamps)
            for previous, current in zip(timestamps, timestamps[1:])
            if current > previous
        ]
        if not intervals:
            raise SynchronizationError(
                "Cannot infer a sampling interval from the IMU timestamps."
            )
        return round(median(intervals))

    def _sample_at(
        self,
        samples: tuple[IMUSample, ...],
        timestamps: tuple[int, ...],
        target_ns: int,
        imu_name: str,
    ) -> IMUSample:
        """
        Return an exact sample or interpolate between adjacent samples.
        """
        index = bisect_left(timestamps, target_ns)

        if index < len(samples) and timestamps[index] == target_ns:
            return samples[index]

        if index == 0 or index >= len(samples):
            raise SynchronizationError(
                f"Cannot interpolate {imu_name} at timestamp "
                f"{target_ns}; target is outside its recorded range."
            )

        first = samples[index - 1]
        second = samples[index]

        gap_ns = second.timestamp_ns - first.timestamp_ns

        if gap_ns > self.maximum_interpolation_gap_ns:
            gap_ms = gap_ns / 1_000_000

            raise SynchronizationError(
                f"{imu_name} contains a {gap_ms:.3f} ms gap near "
                f"timestamp {target_ns}; maximum permitted gap is "
                f"{self.maximum_interpolation_gap_ns / 1_000_000:.3f} ms."
            )

        return self.interpolator.interpolate(
            first=first,
            second=second,
            target_timestamp_ns=target_ns,
        )
