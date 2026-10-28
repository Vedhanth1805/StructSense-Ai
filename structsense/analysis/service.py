"""Orchestrates existing engineering checks and risk logic behind a UI-neutral API."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from environment.building_env import ACTION_NAMES, BuildingStressEnv, PARAM_KEYS
from risk.risk_module import StructuralRiskScorer

class StructuralAnalysisService:
    """Execute the repository's five implemented scenario checks and risk scorer."""
    def analyze(self, parameters: Dict[str, float], scenario: Optional[int] = None,
                include_ppo: bool = False, ppo_timesteps: int = 1024) -> Dict[str, Any]:
        missing = [key for key in PARAM_KEYS if key not in parameters or parameters[key] is None]
        if missing:
            raise ValueError("Analysis requires all 18 parameters; unavailable: " + ", ".join(missing))
        env = BuildingStressEnv(parameters, max_steps=20)
        state, reset_info = env.reset()
        actions = [scenario] if scenario is not None else list(ACTION_NAMES)
        scenario_results = {}
        for action in actions:
            # Independent environment per scenario avoids cumulative damage from
            # one test affecting the next scenario's recorded result.
            check = BuildingStressEnv(parameters, max_steps=20)
            check.reset()
            _, reward, _, _, info = check.step(action)
            scenario_results[ACTION_NAMES[action]] = {**info, "reward": float(reward)}
        scorer = StructuralRiskScorer()
        aggregate_components = scorer.aggregate_components(raw_params=parameters)
        risk = aggregate_components["aggregate_risk"]
        elements = aggregate_components["element_risks"]
        output = {
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "scenario_results": scenario_results,
            "engineering_checks": scenario_results,
            "overall_risk_score": round(risk * 100, 2),
            "risk_label": "HIGH" if risk >= .7 else "MODERATE" if risk >= .4 else "LOW",
            "element_risks": elements,
            "risk_contributions": scorer.component_contributions(raw_params=parameters),
            "aggregate_risk_formula": aggregate_components,
            "environment_baseline": reset_info,
            "limitations": "Research decision-support output; simplified checks are not formal design verification, statutory approval, or finite-element analysis.",
        }
        if include_ppo:
            # Retain the repository's PPO and NeuralDSW implementations. They are
            # opt-in because policy training is materially slower than rule checks.
            from risk.risk_module import load_or_train_dsw
            from agent.ppo_agent import PPOStructuralAgent
            dsw = load_or_train_dsw()
            agent = PPOStructuralAgent(parameters, dsw_model=dsw)
            training = agent.train(timesteps=ppo_timesteps)
            evaluation = agent.evaluate(n_episodes=1)
            episode = agent.run_single_episode()
            dsw_weight = dsw.predict_weight(state)
            output["ppo"] = {"training": training, "evaluation": evaluation, "episode": episode}
            output["neural_dsw"] = {"safety_weight": dsw_weight,
                "provenance": "Persistent shared PyTorch NeuralDSW checkpoint; supervised with binary cross-entropy on synthetic states labelled from StructuralRiskScorer.score() >= 0.55. During PPO training and evaluation its per-state output scales the environment's existing failure penalty by (0.5 + DSW weight), neutral at 0.5. DSW training is independent of PPO rollouts; this is reward integration, not joint RL training, and is not calibrated or validated against field data.",
                "training": dsw.training_metadata}
        return output
