from __future__ import annotations
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.infrastructure import InfrastructureModel
from scrutable.workload import WorkloadRegistry
from scrutable.buffer import ResponseBuffer
from scrutable.simulator import ServiceSimulator
from scrutable.synthesizer import SynthesizerConfig, WorkloadSynthesizer
from scrutable.pathology import PathologyInjector, TimedPathology, StochasticPathology
from scrutable.operations import RolloutSystem, OperationsSystem, SoftwareVersion
from scrutable.detector import Detector
from scrutable.actuator import Actuator
from scrutable.models import WorkloadState


class SimulationEngine:
    def __init__(
        self,
        infra: InfrastructureModel,
        registry: WorkloadRegistry,
        synth_config: SynthesizerConfig,
        versions: dict[str, SoftwareVersion] | None = None,
        seed: int | None = None,
    ) -> None:
        self._rng = np.random.default_rng(seed)
        self._loop = EventLoop()
        self._infra = infra
        self._workload_states: dict[str, WorkloadState] = {
            wid: WorkloadState(wid) for wid in registry.all_ids()
        }
        self._buffer = ResponseBuffer()
        self._simulator = ServiceSimulator(
            self._loop, infra, registry, self._workload_states, self._buffer, self._rng
        )
        self._synthesizer = WorkloadSynthesizer(
            synth_config, self._loop, self._simulator, self._rng
        )
        self._injector = PathologyInjector(
            self._loop, infra, self._workload_states, self._rng
        )
        self._rollouts = RolloutSystem(versions or {}, infra, self._workload_states)
        self._ops = OperationsSystem(infra)
        self._detectors: list[Detector] = []
        self._actuators: list[Actuator] = []

    def add_detector(self, detector: Detector) -> None:
        self._detectors.append(detector)

    def add_actuator(self, actuator: Actuator) -> None:
        self._actuators.append(actuator)

    def add_timed_pathology(self, tp: TimedPathology) -> None:
        self._injector.add_timed(tp)

    def add_stochastic_pathology(self, sp: StochasticPathology) -> None:
        self._injector.add_stochastic(sp)

    @property
    def buffer(self) -> ResponseBuffer:
        return self._buffer

    @property
    def rollouts(self) -> RolloutSystem:
        return self._rollouts

    @property
    def ops(self) -> OperationsSystem:
        return self._ops

    def run(self, until: float) -> None:
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
