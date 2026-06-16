from __future__ import annotations
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.plant import Plant
from scrutable.workload import WorkloadRegistry
from scrutable.observations import ObservationBuffer, NumpyObservationBuffer
from scrutable.simulator import ServiceSimulator
from scrutable.synthesizer import InputProcess
from scrutable.disturbance import DisturbanceInjector, TimedDisturbance, StochasticDisturbance
from scrutable.operations import RolloutSystem, OperationsSystem
from scrutable.sensor import Sensor
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.models import WorkloadState, RolloutState
from scrutable.rollout import Rollout
from scrutable.traffic import WorkloadMix
from scrutable.pipeline import RolloutPipeline


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
        self._buffer = NumpyObservationBuffer()
        self._simulator = ServiceSimulator(
            self._loop, infra, registry, self._workload_states, self._buffer, self._rng
        )
        self._synthesizer = InputProcess(
            mix, self._loop, self._simulator, self._rng
        )
        self._injector = DisturbanceInjector(
            self._loop, infra, self._workload_states, self._rng
        )
        self._rollouts = RolloutSystem()
        self._ops = OperationsSystem(infra)
        self._sensors: list[Sensor] = []
        self._detectors: list[Detector] = []
        self._actuators: list[Actuator] = []
        self._started: bool = False

    def add_sensor(self, sensor: Sensor) -> None:
        if sensor.sampling_period <= 0:
            raise ValueError(
                f"sensor.sampling_period must be > 0, got {sensor.sampling_period!r}"
            )
        self._sensors.append(sensor)

    def add_detector(self, detector: Detector) -> None:
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
        for sensor in self._sensors:
            self._schedule_sensor_tick(sensor, 0.0)
        self._loop.run(until)

    def _schedule_sensor_tick(self, sensor: Sensor, current_time: float) -> None:
        next_tick = current_time + sensor.sampling_period

        def tick(s=sensor, t=next_tick) -> None:
            window = self._buffer.window(t - s.window_size, t)
            signals = s.measure(window)
            for detector in self._detectors:
                alarms = detector.detect(signals)
                for alarm in alarms:
                    for act in self._actuators:
                        act.act(alarm, t, self._rollouts, self._ops)
            self._schedule_sensor_tick(s, t)

        self._loop.schedule(next_tick, tick)

    def add_rollout(self, rollout: Rollout) -> None:
        rollout._activate(self._infra, self._workload_states, self._loop)
        self._rollouts.register(rollout)
        self._schedule_rollout_stage(rollout, stage_idx=0, at=rollout.start_at)

    def add_rollout_pipeline(self, pipeline: RolloutPipeline) -> None:
        pipeline._activate(
            loop=self._loop,
            rng=self._rng,
            add_rollout=self.add_rollout,
            add_actuator=self.add_actuator,
        )

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
