import requests
import time
import json
from datetime import datetime

BASE_URL = "http://localhost:7860"


def wait_for_server():
    print("[INFO] Waiting for server...")
    for _ in range(30):
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                print("[INFO] Server is ready")
                return
        except:
            pass
        time.sleep(1)
    raise Exception("Server failed to start")


def safe_post(url, payload):
    for _ in range(3):
        try:
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code != 200:
                raise Exception(f"Bad status: {r.status_code}")
            return r.json()
        except Exception as e:
            print(f"[WARN] Retry request: {e}")
            time.sleep(1)
    return None


def log(obj):
    print(json.dumps(obj), flush=True)


def run_task(task_id, max_steps):
    log({
        "type": "START",
        "task": task_id,
        "env": "CrisisFlow",
        "model": "safe-agent",
        "timestamp": datetime.utcnow().isoformat()
    })

    reset = safe_post(f"{BASE_URL}/reset", {"task_id": task_id})
    if not reset:
        log({"type": "END", "success": False, "steps": 0, "score": 0.0, "rewards": []})
        return

    session_id = reset.get("session_id")
    if not session_id:
        log({"type": "END", "success": False, "steps": 0, "score": 0.0, "rewards": []})
        return

    rewards = []
    done = False
    step = 0

    while not done and step < max_steps:
        action = {
            "action_type": "wait",
            "zone_id": None,
            "resource_type": None,
            "resource_amount": None,
            "priority": None
        }

        result = safe_post(
            f"{BASE_URL}/step",
            {
                "session_id": session_id,
                "action": action
            }
        )

        if not result:
            log({
                "type": "STEP",
                "step": step + 1,
                "action": action,
                "reward": 0.0,
                "done": True,
                "error": "request_failed"
            })
            break

        reward = result.get("reward", {}).get("score", 0.0)
        done = result.get("done", True)

        rewards.append(reward)
        step += 1

        log({
            "type": "STEP",
            "step": step,
            "action": action,
            "reward": reward,
            "done": done,
            "error": None
        })

        time.sleep(0.2)

    score = sum(rewards)/len(rewards) if rewards else 0.0

    log({
        "type": "END",
        "success": True,
        "steps": step,
        "score": score,
        "rewards": rewards
    })


def main():
    try:
        wait_for_server()

        tasks = {
            "alert_identification": 5,
            "resource_prioritization": 8,
            "full_crisis_management": 12
        }

        for task, steps in tasks.items():
            run_task(task, steps)

        print("[INFO] Inference completed")

    except Exception as e:
        print(f"[FATAL] {e}")


if __name__ == "__main__":
    main()