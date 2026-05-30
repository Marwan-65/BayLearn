#!/usr/bin/env python3
"""
Export baseline questions to JSON for analysis
"""

import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'question-generation-module'))

from app.llm.groq_client import QuestionGenLLMClient
from app.services.prompt_builder import build_mcq_prompt

SAMPLE_STUDY_MATERIAL = """
Physics: Fundamental Principles and Concepts

1. Newton's Laws of Motion
Newton's First Law: An object at rest stays at rest, and an object in motion stays in motion 
unless acted upon by an external force. This law describes the concept of inertia.

Newton's Second Law: The acceleration of an object is directly proportional to the net force 
acting on it and inversely proportional to its mass. Mathematically: F = ma, where F is force, 
m is mass, and a is acceleration.

Newton's Third Law: For every action, there is an equal and opposite reaction. When object A 
exerts a force on object B, object B exerts an equal force in the opposite direction on object A.

2. Kinematics
Kinematics is the study of motion without considering the forces that cause it.
- Displacement: The change in position of an object (vector quantity)
- Velocity: Rate of change of displacement (vector quantity)
- Acceleration: Rate of change of velocity (vector quantity)

Key equations for uniformly accelerated motion:
v = u + at
s = ut + (1/2)at²
v² = u² + 2as

Where: u is initial velocity, v is final velocity, a is acceleration, t is time, s is displacement

3. Energy and Work
Work is done when a force acts on an object and causes displacement in the direction of the force.
W = F × d × cos(θ), where θ is the angle between force and displacement.

Kinetic Energy: The energy of motion. KE = (1/2)mv²
Potential Energy: Energy due to position or configuration. PE = mgh (for gravitational potential energy)

Conservation of Energy: Total mechanical energy (KE + PE) remains constant in a closed system 
without non-conservative forces.

4. Momentum and Collisions
Momentum: The product of mass and velocity. p = mv
Impulse: Change in momentum resulting from a force acting over time. J = FΔt = Δp

Conservation of Momentum: In an isolated system, total momentum before collision equals total 
momentum after collision.

Elastic Collision: Kinetic energy is conserved
Inelastic Collision: Kinetic energy is not conserved (some lost as heat, sound, deformation)

5. Circular Motion and Gravitation
Centripetal Force: Force required to keep an object moving in a circular path. Fc = mv²/r

Gravitational Force: F = G(m₁m₂)/r², where G is the gravitational constant, m₁ and m₂ are masses, 
and r is the distance between centers of mass.

Orbital Motion: Satellites orbit due to balance between gravitational force and required centripetal force.
"""

class GroqQuestionGenerator:
    def __init__(self, api_key: str, model_id: str):
        self.client = QuestionGenLLMClient(api_key=api_key, model_id=model_id)
    
    def generate_questions(self, study_material: str, num_questions: int, difficulty: str) -> list:
        system_prompt, user_prompt = build_mcq_prompt(study_material, num_questions, difficulty)
        raw_response = self.client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.85,
            max_tokens=max(2000, 500 + (num_questions * 300)),
        )
        
        text = raw_response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) > 2:
                text = "\n".join(lines[1:-1])
        
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return []


def main():
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
    GROQ_MODEL_ID = os.getenv("GROQ_MODEL_ID", "llama-3.3-70b-versatile")
    
    generator = GroqQuestionGenerator(api_key=GROQ_API_KEY, model_id=GROQ_MODEL_ID)
    
    baseline_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "model": GROQ_MODEL_ID,
            "type": "baseline_prompt_layer_only",
            "total_questions": 0,
            "study_material_length": len(SAMPLE_STUDY_MATERIAL),
        },
        "easy": [],
        "medium": [],
        "hard": [],
    }
    
    for difficulty in ['easy', 'medium', 'hard']:
        print(f"Generating 5 {difficulty} questions...")
        questions = generator.generate_questions(SAMPLE_STUDY_MATERIAL, 5, difficulty)
        baseline_data[difficulty] = questions
        baseline_data["metadata"]["total_questions"] += len(questions)
        print(f"✓ {len(questions)} questions generated")
    
    output_file = "/mnt/c/Users/salma/Desktop/Spring26/GP/BayLearn/baseline_questions.json"
    with open(output_file, 'w') as f:
        json.dump(baseline_data, f, indent=2)
    
    print(f"\n✓ Baseline questions exported to: {output_file}")
    print(f"  Total: {baseline_data['metadata']['total_questions']} questions")
    
    # Print summary statistics
    print("\nQuestion Summary:")
    for difficulty in ['easy', 'medium', 'hard']:
        count = len(baseline_data[difficulty])
        print(f"  {difficulty.upper()}: {count} questions")


if __name__ == "__main__":
    main()
