import os
import json
import requests
import time
from datetime import datetime


API_BASE = os.getenv("API_BASE_URL", "http://localhost:7860")


def safe_post(url, payload):
    try:
        res = requests.post(url, json=payload, timeout=5)
        return res.json()
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")
        return None


def log_start(task):
    print(json.dumps({
        "type": "START",
        "task": task,
        "env": "CrisisFlow",
        "model": "rule-based",
        "timestamp": datetime.utcnow().isoformat()
    }), flush=True)


def log_step(step, action, reward, done, error=None):
    print(json.dumps({
        "type": "STEP",
        "step": step,
        "action": action,
        "reward": round(reward, 4),
        "done": done,
        "error": error
    }), flush=True)


def log_end(success, steps, score, rewards):
    print(json.dumps({
        "type": "END",
        "success": success,
        "steps": steps,
        "score": round(score, 4),
        "rewards": [round(r, 4) for r in rewards],
        "mean_reward": round(sum(rewards)/len(rewards) if rewards else 0.0, 4)
    }), flush=True)


def get_safe_action():
    return {
        "action_type": "wait",
        "zone_id": None,
        "resource_type": None,
        "resource_amount": None,
        "priority": None
    }


def run_task(task_id, max_steps):
    log_start(task_id)

    reset = safe_post(f"{API_BASE}/reset", {"task_id": task_id})
    if not reset:
        log_end(False, 0, 0.0, [])
        return

    session_id = reset.get("session_id")
    observation = reset.get("observation")

    if not session_id:
        log_end(False, 0, 0.0, [])
        return

    rewards = []
    done = False
    step_count = 0

    while not done and step_count < max_steps:
        action = get_safe_action()

        result = safe_post(
            f"{API_BASE}/step",
            {
                "session_id": session_id,
                "action": action
            }
        )

        if not result:
            log_step(step_count + 1, action, 0.0, True, "request_failed")
            break

        reward = result.get("reward", {}).get("score", 0.0)
        done = result.get("done", True)
        observation = result.get("observation", {})

        rewards.append(reward)
        step_count += 1

        log_step(step_count, action, reward, done)

        time.sleep(0.2)

    score = sum(rewards)/len(rewards) if rewards else 0.0

    log_end(
        success=True,
        steps=step_count,
        score=score,
        rewards=rewards
    )


def main():
    try:
        tasks = {
            "alert_identification": 5,
            "resource_prioritization": 8,
            "full_crisis_management": 12
        }

        for task, steps in tasks.items():
            run_task(task, steps)

        print("[INFO] Inference completed successfully")

    except Exception as e:
        print(f"[FATAL] {e}")


if __name__ == "__main__":
    main()