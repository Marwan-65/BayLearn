"""
mock_api.py
===========
Simulates the question generation module for local testing.

The mock automatically answers after a short delay, simulating a student
thinking and responding. The full session loop runs without any manual
intervention — just start it and watch the steps tick through.

Contract with eppo_inference.py:

    POST /generate
        Body:    { "topic": str, "difficulty": str }
        Waits ANSWER_DELAY seconds (simulating student thinking),
        then returns a weighted random result based on difficulty.
        Returns: { "correct": bool }

In production, replace this file with the real question generation module.
It receives the same POST /generate, delivers the question to the frontend,
waits for the actual student answer, then returns {"correct": bool}.
Everything between receiving /generate and returning the result is internal
to the question generation module — eppo_inference.py doesn't care.

Run:
    pip install flask
    python mock_api.py
"""

import random
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

# Simulated student response time in seconds
ANSWER_DELAY = 2

# Probability of correct answer per difficulty — realistic simulation
P_CORRECT = {
    "Easy":   0.80,
    "Medium": 0.60,
    "Hard":   0.40,
}


@app.route("/generate", methods=["POST"])
def generate():
    """
    Called by eppo_inference.py at each session step.

    Simulates the full question generation + student answer cycle:
      1. Receives topic + difficulty
      2. Waits ANSWER_DELAY seconds (student thinking time)
      3. Returns a weighted random correct/incorrect result

    In production this is replaced by real question generation,
    frontend delivery, and actual student interaction.
    """
    data       = request.get_json(force=True)
    topic      = data.get("topic",      "unknown")
    difficulty = data.get("difficulty", "Medium")

    print(f"  [QUESTION]  topic='{topic}'  difficulty='{difficulty}'")
    print(f"  [THINKING]  simulating {ANSWER_DELAY}s student response time...")

    # simulate student reading and answering the question
    time.sleep(ANSWER_DELAY)

    p_correct = P_CORRECT.get(difficulty, 0.60)
    correct   = random.random() < p_correct

    print(f"  [ANSWER]    correct={correct}  (p={p_correct})")
    return jsonify({"correct": correct}), 200


if __name__ == "__main__":
    print("=" * 55)
    print("  Mock Question Generation API — http://localhost:5000")
    print()
    print(f"  Simulates student thinking for {ANSWER_DELAY}s per question")
    print(f"  then auto-answers based on difficulty:")
    for diff, p in P_CORRECT.items():
        print(f"    {diff:<8} → {int(p*100)}% correct")
    print()
    print("  POST /generate  — receives question, auto-answers")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)