from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.models import Response, Inference
from scrutable.observations import ObservationBuffer


@dataclass
class SloTarget:
    percentile: float   # e.g. 99.9
    threshold: float    # latency threshold in seconds at the given percentile
    window_size: float  # evaluation window in seconds


@dataclass
class LatencySloCalibrator:
    multiplier: float   # threshold = multiplier * observed percentile latency

    def calibrate(
        self,
        buf: ObservationBuffer,
        calibration_end: float,
        percentile: float,
        window_size: float,
    ) -> SloTarget:
        window = buf.window(calibration_end - window_size, calibration_end)
        if not window:
            raise ValueError("No responses in calibration window — cannot calibrate SLO target")
        latencies = np.array([r.latency for r in window])
        p = float(np.percentile(latencies, percentile))
        return SloTarget(
            percentile=percentile,
            threshold=p * self.multiplier,
            window_size=window_size,
        )


@dataclass
class ErrorRateSloTarget:
    threshold: float    # max acceptable error rate (0.0–1.0)
    window_size: float  # evaluation window in seconds


@dataclass
class ErrorRateSloCalibrator:
    multiplier: float   # threshold = multiplier * observed baseline error rate

    def calibrate(
        self,
        buf: ObservationBuffer,
        calibration_end: float,
        window_size: float,
    ) -> ErrorRateSloTarget:
        window = buf.window(calibration_end - window_size, calibration_end)
        if not window:
            raise ValueError("No responses in calibration window — cannot calibrate error rate SLO target")
        error_rate = sum(1 for r in window if r.error_code != 0) / len(window)
        return ErrorRateSloTarget(
            threshold=min(1.0, error_rate * self.multiplier),
            window_size=window_size,
        )


class ErrorRateSloDetector:
    def __init__(
        self,
        detector_id: str,
        target: ErrorRateSloTarget,
        tick_interval: float,
    ) -> None:
        self.detector_id = detector_id
        self.target = target
        self.window_size = target.window_size
        self.tick_interval = tick_interval

    def detect(self, window: list[Response]) -> list[Inference]:
        if not window:
            return []
        error_rate = sum(1 for r in window if r.error_code != 0) / len(window)
        if error_rate <= self.target.threshold:
            return []
        ratio = error_rate / self.target.threshold if self.target.threshold > 0 else float("inf")
        confidence = min(1.0, (ratio - 1.0) / 9.0)
        t_start = min(r.issued_at for r in window)
        t_end = max(r.issued_at + r.latency for r in window)
        return [
            Inference(
                detector_id=self.detector_id,
                pathology_type="error_rate_degradation",
                target_id="cluster",
                target_level="cluster",
                confidence=confidence,
                detected_at=t_end,
                window_start=t_start,
                window_end=t_end,
            )
        ]


class LatencySloDetector:
    def __init__(
        self,
        detector_id: str,
        target: SloTarget,
        tick_interval: float,
    ) -> None:
        self.detector_id = detector_id
        self.target = target
        self.window_size = target.window_size
        self.tick_interval = tick_interval

    def detect(self, window: list[Response]) -> list[Inference]:
        if not window:
            return []
        latencies = np.array([r.latency for r in window])
        p = float(np.percentile(latencies, self.target.percentile))
        if p <= self.target.threshold:
            return []
        ratio = p / self.target.threshold
        confidence = min(1.0, (ratio - 1.0) / 9.0)
        t_start = min(r.issued_at for r in window)
        t_end = max(r.issued_at + r.latency for r in window)
        return [
            Inference(
                detector_id=self.detector_id,
                pathology_type="latency_degradation",
                target_id="cluster",
                target_level="cluster",
                confidence=confidence,
                detected_at=t_end,
                window_start=t_start,
                window_end=t_end,
            )
        ]
