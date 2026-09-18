"""Minimal RL quick intro: Epsilon-Greedy on a Multi-Armed Bandit.

Run this file directly:

  python -m py_notebook.src.reinforcement_learning.main

No third-party dependencies required.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Sequence, Tuple


# Defaults for a short, illustrative run
DEFAULT_PROBABILITIES: Tuple[float, ...] = (0.15, 0.5, 0.3, 0.8, 0.6)
DEFAULT_TOTAL_STEPS: int = 2000
DEFAULT_RANDOM_SEED: int = 7


@dataclass(frozen=True)
class EpsilonSchedule:
    """Exponential decay epsilon schedule.

    epsilon(step) = max(end, start * decay_rate ** step)

    The decay_rate is computed so that epsilon decays from `start` to approximately
    `end` over `decay_steps` steps.
    """

    start: float = 1.0
    end: float = 0.05
    decay_steps: int = 1000

    def value(self, step_index: int) -> float:
        if self.decay_steps <= 0 or self.start <= 0:
            return max(self.end, self.start)
        # Compute a rate so that after decay_steps we are ~end
        # Guard against math domain issues by clamping
        clamped_end = max(min(self.end, self.start), 1e-8)
        decay_rate = (clamped_end / self.start) ** (1.0 / float(self.decay_steps))
        epsilon = self.start * (decay_rate ** float(step_index))
        return max(self.end, epsilon)


class MultiArmedBandit:
    """Bernoulli bandit with fixed success probabilities per arm."""

    def __init__(self, arm_success_probabilities: Sequence[float]):
        if not arm_success_probabilities:
            raise ValueError("At least one arm is required")
        for p in arm_success_probabilities:
            if not (0.0 <= p <= 1.0):
                raise ValueError("Probabilities must be in [0, 1]")
        self._probs: List[float] = list(arm_success_probabilities)

    @property
    def num_arms(self) -> int:
        return len(self._probs)

    @property
    def true_means(self) -> Tuple[float, ...]:
        return tuple(self._probs)

    def pull(self, arm_index: int) -> float:
        if not (0 <= arm_index < self.num_arms):
            raise IndexError("Invalid arm index")
        p = self._probs[arm_index]
        return 1.0 if random.random() < p else 0.0


class EpsilonGreedyAgent:
    """Epsilon-Greedy bandit agent with incremental mean updates."""

    def __init__(self, num_arms: int, epsilon_schedule: EpsilonSchedule):
        if num_arms <= 0:
            raise ValueError("num_arms must be positive")
        self._num_arms = num_arms
        self._epsilon_schedule = epsilon_schedule
        self._action_counts: List[int] = [0 for _ in range(num_arms)]
        self._action_value_estimates: List[float] = [0.0 for _ in range(num_arms)]

    @property
    def action_counts(self) -> Tuple[int, ...]:
        return tuple(self._action_counts)

    @property
    def action_value_estimates(self) -> Tuple[float, ...]:
        return tuple(self._action_value_estimates)

    def select_action(self, step_index: int) -> int:
        epsilon = self._epsilon_schedule.value(step_index)
        explore = random.random() < epsilon
        if explore:
            return random.randrange(self._num_arms)
        # Exploit: choose argmax of current value estimates
        best_value = -math.inf
        best_arm = 0
        for arm_index, estimate in enumerate(self._action_value_estimates):
            if estimate > best_value:
                best_value = estimate
                best_arm = arm_index
        return best_arm

    def update(self, arm_index: int, reward: float) -> None:
        self._action_counts[arm_index] += 1
        count = self._action_counts[arm_index]
        old_estimate = self._action_value_estimates[arm_index]
        # Incremental mean update
        step_size = 1.0 / float(count)
        self._action_value_estimates[arm_index] = old_estimate + step_size * (
            reward - old_estimate
        )


def run_bandit_experiment(
    arm_probabilities: Sequence[float] = DEFAULT_PROBABILITIES,
    total_steps: int = DEFAULT_TOTAL_STEPS,
    random_seed: int = DEFAULT_RANDOM_SEED,
    epsilon_schedule: EpsilonSchedule | None = None,
) -> None:
    random.seed(random_seed)

    bandit = MultiArmedBandit(arm_probabilities)
    schedule = epsilon_schedule or EpsilonSchedule(start=1.0, end=0.05, decay_steps=1000)
    agent = EpsilonGreedyAgent(num_arms=bandit.num_arms, epsilon_schedule=schedule)

    optimal_arm = max(range(bandit.num_arms), key=lambda i: bandit.true_means[i])
    optimal_mean = bandit.true_means[optimal_arm]

    cumulative_reward = 0.0
    cumulative_regret = 0.0

    for step in range(total_steps):
        arm = agent.select_action(step)
        reward = bandit.pull(arm)
        agent.update(arm, reward)

        cumulative_reward += reward
        cumulative_regret += (optimal_mean - reward)

        # Print a very small status occasionally to keep output light
        if (step + 1) % (total_steps // 4 or 1) == 0:
            avg = cumulative_reward / float(step + 1)
            print(
                f"Step {step + 1:4d} | avg_reward={avg:.3f} | "
                f"epsilon={schedule.value(step):.3f}"
            )

    print()
    print("True means per arm:")
    print(" ".join(f"{m:.2f}" for m in bandit.true_means))
    print("Estimated values per arm:")
    print(" ".join(f"{v:.2f}" for v in agent.action_value_estimates))
    print("Times each arm was selected:")
    print(" ".join(str(c) for c in agent.action_counts))

    print()
    print(f"Optimal arm: {optimal_arm} with true mean {optimal_mean:.2f}")
    print(f"Total steps: {total_steps}")
    print(f"Cumulative reward: {cumulative_reward:.1f}")
    print(f"Average reward: {cumulative_reward / float(total_steps):.3f}")
    print(f"Cumulative regret (lower is better): {cumulative_regret:.1f}")


def main() -> None:
    run_bandit_experiment()


if __name__ == "__main__":
    main()