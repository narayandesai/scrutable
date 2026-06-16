from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Callable
import numpy as np
from scrutable.event_loop import EventLoop
from scrutable.models import Disturbance, Release, ReleaseChange, RolloutState
from scrutable.rollout import AlarmLog, GateCallback, Rollout, RolloutActuator


@dataclass
class ChangeStream:
    change_rate: float
    bug_fraction: float
    disturbance_factory: Callable[[str], Disturbance]

    def next_arrival_delay(self, rng: np.random.Generator) -> float:
        return float(rng.exponential(1.0 / self.change_rate))

    def generate_change(self, change_id: str, rng: np.random.Generator) -> ReleaseChange:
        has_bug = float(rng.random()) < self.bug_fraction
        disturbance = self.disturbance_factory(change_id) if has_bug else None
        return ReleaseChange(change_id=change_id, disturbance=disturbance)


class ReleaseBundler:
    def __init__(self, bundle_size: int) -> None:
        self._bundle_size = bundle_size
        self._changes: list[ReleaseChange] = []
        self._release_count = 0

    def add(self, change: ReleaseChange) -> Release | None:
        self._changes.append(change)
        if len(self._changes) >= self._bundle_size:
            return self._flush()
        return None

    def _flush(self) -> Release:
        self._release_count += 1
        release = Release(
            release_id=f"r{self._release_count}",
            changes=list(self._changes),
        )
        self._changes.clear()
        return release


@dataclass
class DebugCycle:
    median_seconds: float = 6.0 * 3600.0
    sigma: float = 0.84

    def sample_duration(self, rng: np.random.Generator) -> float:
        mu = np.log(self.median_seconds)
        return float(rng.lognormal(mu, self.sigma))


class RolloutPipeline:
    def __init__(
        self,
        change_stream: ChangeStream,
        bundler: ReleaseBundler,
        cluster_order: list[str],
        bake_duration: float,
        alarm_log: AlarmLog,
        debug_cycle: DebugCycle,
        rollback_duration: float = 3600.0,
    ) -> None:
        self._change_stream = change_stream
        self._bundler = bundler
        self._cluster_order = cluster_order
        self._bake_duration = bake_duration
        self._alarm_log = alarm_log
        self._debug_cycle = debug_cycle
        self._rollback_duration = rollback_duration

        self._pending: deque[Release] = deque()
        self._active_rollout: Rollout | None = None
        self._rollback_done = False
        self._debug_done = False

        self._loop: EventLoop | None = None
        self._rng: np.random.Generator | None = None
        self._add_rollout: Callable[[Rollout], None] | None = None
        self._add_actuator: Callable[[object], None] | None = None
        self._change_counter = 0

        # metrics
        self.releases_attempted = 0
        self.releases_completed = 0
        self.releases_rolled_back = 0
        self.debug_durations: list[float] = []

    def _activate(
        self,
        loop: EventLoop,
        rng: np.random.Generator,
        add_rollout: Callable[[Rollout], None],
        add_actuator: Callable[[object], None],
    ) -> None:
        self._loop = loop
        self._rng = rng
        self._add_rollout = add_rollout
        self._add_actuator = add_actuator
        self._schedule_next_change(loop.now)

    def _schedule_next_change(self, current_time: float) -> None:
        assert self._loop is not None and self._rng is not None
        delay = self._change_stream.next_arrival_delay(self._rng)
        next_time = current_time + delay
        self._loop.schedule(next_time, lambda t=next_time: self._on_change_arrives(t))

    def _on_change_arrives(self, sim_time: float) -> None:
        assert self._rng is not None
        self._change_counter += 1
        change = self._change_stream.generate_change(f"ch{self._change_counter}", self._rng)
        release = self._bundler.add(change)
        if release is not None:
            debug_in_progress = self._rollback_done or self._debug_done
            if self._active_rollout is None and not debug_in_progress:
                self._start_rollout(release, sim_time)
            else:
                self._pending.append(release)
        self._schedule_next_change(sim_time)

    def _start_rollout(self, release: Release, sim_time: float) -> None:
        assert self._add_rollout is not None and self._add_actuator is not None
        self.releases_attempted += 1

        canary_deploy_time = sim_time
        gates: list[list[GateCallback]] = [[] for _ in self._cluster_order]
        if len(self._cluster_order) > 1:
            gates[1] = [
                lambda status, t, dt=canary_deploy_time: not self._alarm_log.any_since(dt)
            ]

        rollout = Rollout(
            release=release,
            cluster_order=self._cluster_order,
            stage_interval=self._bake_duration,
            start_at=sim_time,
            gates=gates,
            on_complete=self._on_rollout_complete,
        )
        # Set the loop directly so begin_rollback works even without a full plant
        rollout._loop = self._loop

        actuator = RolloutActuator(
            rollout=rollout,
            alarm_log=self._alarm_log,
            rollback_duration=self._rollback_duration,
            on_failure=self._on_failure,
        )
        self._active_rollout = rollout
        self._add_rollout(rollout)
        self._add_actuator(actuator)

    def _on_rollout_complete(self, state: RolloutState, sim_time: float) -> None:
        self._active_rollout = None
        if state == RolloutState.COMPLETED:
            self.releases_completed += 1
            if self._pending:
                self._start_rollout(self._pending.popleft(), sim_time)
        elif state == RolloutState.ROLLED_BACK:
            self.releases_rolled_back += 1
            self._rollback_done = True
            self._try_start_next(sim_time)

    def _on_failure(self, failed_release: Release, sim_time: float) -> None:
        assert self._loop is not None and self._rng is not None
        fixed_changes = [
            ReleaseChange(change_id=ch.change_id, disturbance=None)
            for ch in failed_release.changes
        ]
        fixed_release = Release(
            release_id=f"{failed_release.release_id}-fix",
            changes=fixed_changes,
        )
        self._rollback_done = False
        self._debug_done = False
        duration = self._debug_cycle.sample_duration(self._rng)
        self.debug_durations.append(duration)
        done_at = sim_time + duration
        self._loop.schedule(
            done_at,
            lambda t=done_at, r=fixed_release: self._on_debug_done(r, t),
        )

    def _on_debug_done(self, fixed_release: Release, sim_time: float) -> None:
        self._pending.appendleft(fixed_release)
        self._debug_done = True
        self._try_start_next(sim_time)

    def _try_start_next(self, sim_time: float) -> None:
        if self._rollback_done and self._debug_done and self._pending:
            self._rollback_done = False
            self._debug_done = False
            self._start_rollout(self._pending.popleft(), sim_time)
