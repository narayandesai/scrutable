from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scrutable.models import Response, Inference
from scrutable.observations import ObservationBuffer


@dataclass
class SloThresholds:
    p999_latency: float  # P99.9 latency threshold in seconds


@dataclass
class BurnInCalibrator:
    window_size: float   # seconds of burn-in data to use
    multiplier: float    # threshold = multiplier * observed P99.9

    def calibrate(self, buf: ObservationBuffer, burn_in_end: float) -> SloThresholds:
        window = buf.window(burn_in_end - self.window_size, burn_in_end)
        if not window:
            raise ValueError("No responses in burn-in window — cannot calibrate SLO thresholds")
        latencies = np.array([r.latency for r in window])
        p999 = float(np.percentile(latencies, 99.9))
        return SloThresholds(p999_latency=p999 * self.multiplier)


class LatencySloDetector:
    def __init__(
        self,
        detector_id: str,
        thresholds: SloThresholds,
        window_size: float,
        tick_interval: float,
    ) -> None:
        self.detector_id = detector_id
        self.thresholds = thresholds
        self.window_size = window_size
        self.tick_interval = tick_interval

    def detect(self, window: list[Response]) -> list[Inference]:
        if not window:
            return []
        latencies = np.array([r.latency for r in window])
        p999 = float(np.percentile(latencies, 99.9))
        if p999 <= self.thresholds.p999_latency:
            return []
        # confidence: clamped ratio of how far above threshold
        ratio = p999 / self.thresholds.p999_latency
        confidence = min(1.0, (ratio - 1.0) / 9.0)  # reaches 1.0 at 10x threshold
        t_start = window[0].issued_at
        t_end = window[-1].issued_at + window[-1].latency
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
