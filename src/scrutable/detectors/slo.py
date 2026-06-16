from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.models import Signal, Alarm
from scrutable.observations import ObservationBuffer
from scrutable.window_result import WindowResult


@dataclass
class SloTarget:
    percentile: float
    threshold: float
    window_size: float


class PercentileRecorderSensor:
    """Accumulates per-window percentile values for calibration; emits no signals.

    Add this sensor to a calibration engine.  After the engine run, pass
    ``recorded_values`` to ``LatencySloCalibrator.calibrate_from_values``.
    Using this sensor together with ``SimulationEngine(buffer_max_age=window_size)``
    keeps the observation buffer at O(rate × window_size) rather than O(rate × duration).
    """

    def __init__(self, percentile: float, window_size: float) -> None:
        self.sensor_id = "percentile-recorder"
        self.window_size = window_size
        self.sampling_period = window_size
        self._percentile = percentile
        self.recorded_values: list[float] = []

    def measure(self, window: WindowResult) -> list[Signal]:
        if window:
            self.recorded_values.append(window.percentile(self._percentile))
        return []


@dataclass
class LatencySloCalibrator:
    target_fpr: float = 0.001
    max_daily_alerts: float | None = None
    max_alerts_per_bake: float | None = None
    bake_duration: float | None = None

    def _effective_fpr(self, window_size: float) -> float:
        """Return the strictest per-window FPR across all three constraints."""
        fpr = self.target_fpr
        if self.max_daily_alerts is not None:
            fpr = min(fpr, self.max_daily_alerts * window_size / 86400.0)
        if self.max_alerts_per_bake is not None and self.bake_duration is not None:
            fpr = min(fpr, self.max_alerts_per_bake * window_size / self.bake_duration)
        return fpr

    def calibrate(
        self,
        buf: ObservationBuffer,
        calibration_end: float,
        percentile: float,
        window_size: float,
    ) -> SloTarget:
        estimates: list[float] = []
        t = 0.0
        while t + window_size <= calibration_end:
            window = buf.window(t, t + window_size)
            if window:
                estimates.append(window.percentile(percentile))
            t += window_size
        return self.calibrate_from_values(estimates, percentile, window_size)

    def calibrate_from_values(
        self,
        values: list[float],
        percentile: float,
        window_size: float,
    ) -> SloTarget:
        if len(values) < 2:
            raise ValueError(
                f"Empirical calibration needs ≥2 windows but got {len(values)}. "
                f"Increase calibration_duration beyond {2 * window_size:.1f}s or reduce window_size."
            )
        effective_fpr = self._effective_fpr(window_size)
        threshold = float(np.percentile(values, (1.0 - effective_fpr) * 100.0))
        return SloTarget(percentile=percentile, threshold=threshold, window_size=window_size)


class LatencySloSensor:
    def __init__(self, sensor_id: str, target: SloTarget, sampling_period: float) -> None:
        self.sensor_id = sensor_id
        self.window_size = target.window_size
        self.sampling_period = sampling_period
        self._percentile = target.percentile

    def measure(self, window: WindowResult) -> list[Signal]:
        if not window:
            return []
        return [Signal(
            sensor_id=self.sensor_id,
            metric=f"latency_p{self._percentile}",
            value=window.percentile(self._percentile),
            window_start=window.t_start,
            window_end=window.t_end,
            sample_count=len(window),
        )]


class LatencySloDetector:
    def __init__(self, detector_id: str, target: SloTarget) -> None:
        self.detector_id = detector_id
        self._target = target
        self._metric = f"latency_p{target.percentile}"

    def detect(self, signals: list[Signal]) -> list[Alarm]:
        for signal in signals:
            if signal.metric != self._metric:
                continue
            if signal.value <= self._target.threshold:
                continue
            ratio = signal.value / self._target.threshold
            severity = min(1.0, (ratio - 1.0) / 9.0)
            return [Alarm(
                detector_id=self.detector_id,
                fault_type="latency_degradation",
                target_id="cluster",
                target_level="cluster",
                severity=severity,
                detected_at=signal.window_end,
                window_start=signal.window_start,
                window_end=signal.window_end,
            )]
        return []


@dataclass
class ErrorRateSloTarget:
    threshold: float
    window_size: float


@dataclass
class ErrorRateSloCalibrator:
    multiplier: float

    def calibrate(
        self,
        buf: ObservationBuffer,
        calibration_end: float,
        window_size: float,
    ) -> ErrorRateSloTarget:
        window = buf.window(calibration_end - window_size, calibration_end)
        if not window:
            raise ValueError(
                "No responses in calibration window — cannot calibrate error rate SLO target"
            )
        return ErrorRateSloTarget(
            threshold=min(1.0, window.error_rate * self.multiplier),
            window_size=window_size,
        )


class ErrorRateSloSensor:
    def __init__(self, sensor_id: str, target: ErrorRateSloTarget, sampling_period: float) -> None:
        self.sensor_id = sensor_id
        self.window_size = target.window_size
        self.sampling_period = sampling_period

    def measure(self, window: WindowResult) -> list[Signal]:
        if not window:
            return []
        return [Signal(
            sensor_id=self.sensor_id,
            metric="error_rate",
            value=window.error_rate,
            window_start=window.t_start,
            window_end=window.t_end,
            sample_count=len(window),
        )]


class ErrorRateSloDetector:
    def __init__(self, detector_id: str, target: ErrorRateSloTarget) -> None:
        self.detector_id = detector_id
        self._target = target

    def detect(self, signals: list[Signal]) -> list[Alarm]:
        for signal in signals:
            if signal.metric != "error_rate":
                continue
            if signal.value <= self._target.threshold:
                continue
            ratio = (signal.value / self._target.threshold
                     if self._target.threshold > 0 else float("inf"))
            severity = min(1.0, (ratio - 1.0) / 9.0)
            return [Alarm(
                detector_id=self.detector_id,
                fault_type="error_rate_degradation",
                target_id="cluster",
                target_level="cluster",
                severity=severity,
                detected_at=signal.window_end,
                window_start=signal.window_start,
                window_end=signal.window_end,
            )]
        return []
