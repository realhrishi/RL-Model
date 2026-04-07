from dotenv import load_dotenv
load_dotenv()

import os
import json
import requests
import sys
from datetime import datetime
from openai import OpenAI

# Required Environment Variables
API_BASE_URL = os.environ.get("API_BASE_URL")
MODEL_NAME = os.environ.get("MODEL_NAME")
HF_TOKEN = os.environ.get("HF_TOKEN")

if not API_BASE_URL or not MODEL_NAME or not HF_TOKEN:
    sys.stderr.write("[DEBUG] Missing required environment vars: API_BASE_URL, MODEL_NAME, HF_TOKEN\n")
    sys.exit(1)

def log_start(task: str, env: str, model: str):
    print(json.dumps({
        "type": "START",
        "task": task,
        "env": env,
        "model": model,
        "timestamp": datetime.utcnow().isoformat()
    }), flush=True)

def log_step(step: int, action: dict, reward: float, done: bool, error=None):
    print(json.dumps({
        "type": "STEP",
        "step": step,
        "action": action,
        "reward": round(reward, 4),
        "done": done,
        "error": error
    }), flush=True)

def log_end(success: bool, steps: int, score: float, rewards: list[float]):
    print(json.dumps({
        "type": "END",
        "success": success,
        "steps": steps,
        "score": round(score, 4),
        "rewards": [round(r, 4) for r in rewards],
        "mean_reward": round(sum(rewards)/len(rewards) if rewards else 0.0, 4)
    }), flush=True)

SYSTEM_PROMPT = """You are an expert disaster response coordinator managing a flood crisis.

You will receive the current state of 5 city zones as JSON.

Respond with ONLY a valid JSON action object:
{
  "action_type": "dispatch_rescue" | "send_alert" | "allocate_resource" | "wait",
  "zone_id": "NORTH" | "SOUTH" | "EAST" | "WEST" | "CENTER" | null,
  "resource_type": "medical" | "food" | "shelter" | null,
  "resource_amount": integer | null,
  "priority": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | null
}

Strategy:
- PRIORITIZE CRITICAL zones (>0.7 flood_level)
- CASCADING FLOODS: CRITICAL zones spread risk to neighbors
- SEND ALERTS BEFORE rescues
- DO NOT ignore same high-risk zone repeatedly
- DO NOT wait if any zone > 0.6
- Avoid duplicate alerts
- Use resources early before decay

Return ONLY JSON.
"""

def call_llm(client: OpenAI, observation: dict) -> dict:
    fallback = {
        "action_type": "wait",
        "zone_id": None,
        "resource_type": None,
        "resource_amount": None,
        "priority": None
    }

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(observation)}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        action = json.loads(content)

        # 🔥 VALIDATION FIX (CRITICAL)
        if not isinstance(action, dict) or "action_type" not in action:
            return fallback

        return action

    except Exception as e:
        sys.stderr.write(f"[DEBUG] LLM call failed: {str(e)}\n")
        return fallback


def main():
    client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)
    base_url = "http://localhost:7860"

    MAX_STEPS_MAP = {
        "alert_identification": 5,
        "resource_prioritization": 8,
        "full_crisis_management": 12
    }

    for task_id in ["alert_identification", "resource_prioritization", "full_crisis_management"]:
        log_start(task=task_id, env="CrisisFlow", model=MODEL_NAME)

        try:
            reset_resp = requests.post(f"{base_url}/reset", json={"task_id": task_id, "seed": 42})
            reset_resp.raise_for_status()

            data = reset_resp.json()
            session_id = data["session_id"]
            observation = data["observation"]

        except Exception as e:
            sys.stderr.write(f"[DEBUG] Reset failed: {str(e)}\n")
            log_end(success=False, steps=0, score=0.0, rewards=[])
            continue

        rewards = []
        steps_taken = 0
        done = False

        while not done and steps_taken < MAX_STEPS_MAP[task_id]:
            action_json = call_llm(client, observation)

            try:
                step_resp = requests.post(
                    f"{base_url}/step",
                    json={"session_id": session_id, "action": action_json}
                )
                step_resp.raise_for_status()

                result = step_resp.json()
                reward = result["reward"]["score"]
                done = result["done"]
                observation = result["observation"]

                rewards.append(reward)
                steps_taken += 1

                log_step(
                    step=steps_taken,
                    action=action_json,
                    reward=reward,
                    done=done
                )

            except Exception as e:
                sys.stderr.write(f"[DEBUG] Step failed: {str(e)}\n")
                log_step(
                    step=steps_taken + 1,
                    action=action_json,
                    reward=0.0,
                    done=True,
                    error=str(e)
                )
                break

        score = sum(rewards) / len(rewards) if rewards else 0.0
        success = score >= 0.5

        log_end(
            success=success,
            steps=steps_taken,
            score=score,
            rewards=rewards
        )


if __name__ == "__main__":
    main()