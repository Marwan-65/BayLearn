"""
Mock API Server for EPPO Inference Testing
==========================================
Mocks the two endpoints expected by eppo_inference.py:

  POST http://localhost:5000/generate   <- receives {topic, difficulty}
  GET  http://localhost:5000/answer     <- returns  {correct: bool}  (random)

Run this in a separate terminal before running eppo_inference.py:
    python mock_api.py

Install Flask if needed:
    pip install flask
"""

import random
from flask import Flask, request, jsonify

app = Flask(__name__)

# Tracks the last question sent (just for logging clarity)
_last_question = {}


@app.route("/generate", methods=["POST"])
def generate():
    """
    Receives {topic: str, difficulty: str} from the RL agent.
    In production this would trigger question generation.
    Here we just log it and return 200 OK.
    """
    global _last_question
    data = request.get_json(force=True)
    topic      = data.get("topic", "unknown")
    difficulty = data.get("difficulty", "unknown")
    _last_question = {"topic": topic, "difficulty": difficulty}
    print(f"  [GENERATE] topic='{topic}'  difficulty='{difficulty}'")
    return jsonify({"status": "ok", "topic": topic, "difficulty": difficulty}), 200


@app.route("/answer", methods=["GET"])
def answer():
    """
    Returns a random correct/incorrect answer.
    Probability is weighted by difficulty so the simulation feels realistic:
      Easy   -> 75% correct
      Medium -> 60% correct
      Hard   -> 45% correct
    """
    diff = _last_question.get("difficulty", "Medium")
    p_correct = {"Easy": 0.75, "Medium": 0.60, "Hard": 0.45}.get(diff, 0.60)
    correct = random.random() < p_correct
    print(f"  [ANSWER]   difficulty='{diff}'  correct={correct}  (p={p_correct})")
    return jsonify({"correct": correct}), 200


if __name__ == "__main__":
    print("Mock API server running on http://localhost:5000")
    print("  POST /generate  — receives topic + difficulty")
    print("  GET  /answer    — returns random {correct: bool}")
    print("Press Ctrl+C to stop.\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
