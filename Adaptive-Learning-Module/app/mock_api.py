

import random
import time
from flask import Flask, request, jsonify

app = Flask(__name__)


ANSWER_DELAY = 2

P_CORRECT = {
    "Easy":   0.80,
    "Medium": 0.60,
    "Hard":   0.40,
}


@app.route("/generate", methods=["POST"])
def generate():

    data       = request.get_json(force=True)
    topic      = data.get("topic",      "unknown")
    difficulty = data.get("difficulty", "Medium")
    file_ids   = data.get("file_ids",   [])

    if isinstance(file_ids, str):
        file_ids = [v.strip() for v in file_ids.split(",") if v.strip()]
    elif not isinstance(file_ids, list):
        file_ids = []

    print(f"  [QUESTION]  topic='{topic}'  difficulty='{difficulty}'")
    if file_ids:
        print(f"  [SCOPE]     file_ids={file_ids}")
    print(f"  [THINKING]  simulating {ANSWER_DELAY}s student response time...")

   
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