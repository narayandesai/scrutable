from __future__ import annotations
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.plant import Plant
from scrutable.workload import WorkloadRegistry
from scrutable.observations import ObservationBuffer
from scrutable.simulator import ServiceSimulator
from scrutable.synthesizer import InputSynthesizer
from scrutable.disturbance import DisturbanceInjector, TimedDisturbance, StochasticDisturbance
from scrutable.operations import RolloutSystem, OperationsSystem
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.models import WorkloadState, RolloutState
from scrutable.rollout import Rollout
from scrutable.traffic import WorkloadMix


class SimulationEngine:
    def __init__(
        self,
        infra: Plant,
        mix: WorkloadMix,
        seed: int | None = None,
    ) -> None:
        self._rng = np.random.default_rng(seed)
        self._loop = EventLoop()
        self._infra = infra
        self._workload_states: dict[str, WorkloadState] = {
            entry.model.workload_id: WorkloadState(entry.model.workload_id)
            for entry in mix.entries
        }
        registry = WorkloadRegistry()
        for entry in mix.entries:
            registry.register(entry.model)
        self._buffer = ObservationBuffer()
        self._simulator = ServiceSimulator(
            self._loop, infra, registry, self._workload_states, self._buffer, self._rng
        )
        self._synthesizer = InputSynthesizer(
            mix, self._loop, self._simulator, self._rng
        )
        self._injector = DisturbanceInjector(
            self._loop, infra, self._workload_states, self._rng
        )
        self._rollouts = RolloutSystem()
        self._ops = OperationsSystem(infra)
        self._detectors: list[Detector] = []
        self._actuators: list[Actuator] = []
        self._started: bool = False

    def add_detector(self, detector: Detector) -> None:
        if detector.tick_interval <= 0:
            raise ValueError(
                f"detector.tick_interval must be > 0, got {detector.tick_interval!r}"
            )
        self._detectors.append(detector)

    def add_actuator(self, actuator: Actuator) -> None:
        self._actuators.append(actuator)

    def add_timed_disturbance(self, td: TimedDisturbance) -> None:
        self._injector.add_timed(td)

    def add_stochastic_disturbance(self, sd: StochasticDisturbance) -> None:
        self._injector.add_stochastic(sd)

    @property
    def buffer(self) -> ObservationBuffer:
        return self._buffer

    @property
    def rollouts(self) -> RolloutSystem:
        return self._rollouts

    @property
    def ops(self) -> OperationsSystem:
        return self._ops

    def run(self, until: float) -> None:
        if self._started:
            raise RuntimeError("SimulationEngine.run called more than once")
        self._started = True
        self._synthesizer.start()
        for detector in self._detectors:
            self._schedule_detector_tick(detector, 0.0)
        self._loop.run(until)

    def _schedule_detector_tick(self, detector: Detector, current_time: float) -> None:
        next_tick = current_time + detector.tick_interval

        def tick(d=detector, t=next_tick) -> None:
            window = self._buffer.window(t - d.window_size, t)
            inferences = d.detect(window)
            for inf in inferences:
                for act in self._actuators:
                    act.act(inf, t, self._rollouts, self._ops)
            self._schedule_detector_tick(d, t)

        self._loop.schedule(next_tick, tick)

    def add_rollout(self, rollout: Rollout) -> None:
        rollout._activate(self._infra, self._workload_states)
        self._rollouts.register(rollout)
        self._schedule_rollout_stage(rollout, stage_idx=0, at=rollout.start_at)

    def _schedule_rollout_stage(self, rollout: Rollout, stage_idx: int, at: float) -> None:
        def advance():
            status = rollout.status
            if status.state not in (RolloutState.PENDING, RolloutState.IN_PROGRESS):
                return
            if not rollout._check_gates(stage_idx, self._loop.now):
                rollout.halt(self._loop.now)
                return
            rollout._deploy_stage(stage_idx, self._loop.now)
            next_idx = stage_idx + 1
            if next_idx < len(rollout.cluster_order):
                self._schedule_rollout_stage(
                    rollout, next_idx, self._loop.now + rollout.stage_interval
                )
        self._loop.schedule(at, advance)
