#!/usr/bin/env python3
"""
Baseline Question Generation Analysis
Generates 5 easy, 5 medium, and 5 hard questions to establish baseline quality.
Creates a PDF report for analysis.
"""

import json
import sys
import os
from datetime import datetime
from typing import List, Optional
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'question-generation-module'))

from app.llm.groq_client import QuestionGenLLMClient
from app.services.prompt_builder import (
    build_mcq_prompt,
    build_short_answer_prompt,
    build_true_false_prompt,
)
from app.models.schemas import GeneratedQuestion, QuestionOption
import json

# ============================================================================
# SAMPLE STUDY MATERIAL (for baseline testing)
# ============================================================================
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

# ============================================================================
# QUESTION GENERATION
# ============================================================================
class GroqQuestionGenerator:
    def __init__(self, api_key: str, model_id: str):
        self.client = QuestionGenLLMClient(api_key=api_key, model_id=model_id)
    
    def generate_questions(
        self, 
        study_material: str, 
        num_questions: int, 
        difficulty: str,
        question_type: str = "mcq"
    ) -> List[dict]:
        """Generate questions using Groq LLM."""
        
        if question_type == "mcq":
            system_prompt, user_prompt = build_mcq_prompt(study_material, num_questions, difficulty)
        elif question_type == "short_answer":
            system_prompt, user_prompt = build_short_answer_prompt(study_material, num_questions, difficulty)
        else:
            system_prompt, user_prompt = build_true_false_prompt(study_material, num_questions, difficulty)
        
        # Increase max_tokens significantly to avoid truncation
        raw_response = self.client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.85,
            max_tokens=max(2000, 500 + (num_questions * 300)),  # Much higher limit
        )
        
        # Parse JSON response with better error handling
        text = raw_response.strip()
        
        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Skip the first line (```json or ```) and last line (```)
            if len(lines) > 2:
                text = "\n".join(lines[1:-1])
        
        try:
            data = json.loads(text)
            return data
        except json.JSONDecodeError as e:
            print(f"  DEBUG: JSON parsing failed")
            print(f"  Response length: {len(raw_response)}")
            print(f"  Last 300 chars: {raw_response[-300:]}")
            print(f"  Error: {e}")
            # Return empty list on error instead of crashing
            return []


# ============================================================================
# PDF GENERATION
# ============================================================================
def generate_baseline_pdf(questions_by_difficulty: dict, output_path: str):
    """Generate a PDF report with questions organized by difficulty."""
    
    pdf = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=HexColor('#1f4788'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=white,
        spaceAfter=10,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    
    question_style = ParagraphStyle(
        'QuestionStyle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=6,
        alignment=TA_JUSTIFY,
        fontName='Helvetica'
    )
    
    # Title
    story.append(Paragraph("BayLearn — Question Generation Baseline Analysis", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    # Overview section
    story.append(Paragraph("Baseline Overview", section_style))
    story.append(Paragraph(
        "<b>Purpose:</b> This document establishes the baseline quality of questions generated using the <i>prompt layer only</i> "
        "approach (no improvement layers). This baseline will be used to measure the impact of adding layers like context enrichment, "
        "semantic validation, and quality scoring.",
        question_style
    ))
    story.append(Paragraph(
        "<b>Configuration:</b> All questions generated from uniform study material (Physics fundamentals) using the Groq LLM "
        "(llama-3.3-70b-versatile) with temperature=0.85.",
        question_style
    ))
    story.append(Spacer(1, 0.2*inch))
    
    # Questions organized by difficulty
    for difficulty in ['easy', 'medium', 'hard']:
        difficulty_upper = difficulty.upper()
        color = {
            'easy': HexColor('#27ae60'),    # Green
            'medium': HexColor('#f39c12'),  # Orange
            'hard': HexColor('#e74c3c'),    # Red
        }[difficulty]
        
        # Difficulty section header
        section_heading = Table(
            [['  ' + difficulty_upper + ' DIFFICULTY  ']],
            colWidths=[7.5*inch],
        )
        section_heading.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), color),
            ('TEXTCOLOR', (0, 0), (-1, -1), white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(section_heading)
        story.append(Spacer(1, 0.15*inch))
        
        questions = questions_by_difficulty.get(difficulty, [])
        
        for i, q in enumerate(questions, 1):
            # Question number and text
            q_text = f"<b>Q{i}:</b> {q.get('question_text', '')}"
            story.append(Paragraph(q_text, question_style))
            
            # Options (if MCQ)
            if 'options' in q and q['options']:
                for opt in q['options']:
                    opt_text = f"<b>{opt.get('label', '')}</b>. {opt.get('text', '')}"
                    story.append(Paragraph(opt_text, ParagraphStyle(
                        'OptionStyle',
                        parent=styles['Normal'],
                        fontSize=10,
                        leftIndent=0.3*inch,
                        spaceAfter=4,
                    )))
            
            # Answer and explanation
            answer = q.get('correct_answer', '')
            explanation = q.get('explanation', '')
            
            story.append(Paragraph(
                f"<b>Correct Answer:</b> {answer}",
                ParagraphStyle(
                    'AnswerStyle',
                    parent=styles['Normal'],
                    fontSize=10,
                    leftIndent=0.2*inch,
                    spaceAfter=3,
                    textColor=HexColor('#27ae60'),
                    fontName='Helvetica-Bold'
                )
            ))
            
            story.append(Paragraph(
                f"<b>Explanation:</b> {explanation}",
                ParagraphStyle(
                    'ExplanationStyle',
                    parent=styles['Normal'],
                    fontSize=9,
                    leftIndent=0.2*inch,
                    spaceAfter=10,
                    textColor=HexColor('#555555'),
                )
            ))
            
            story.append(Spacer(1, 0.1*inch))
        
        story.append(Spacer(1, 0.2*inch))
    
    # Footer with analysis notes
    story.append(PageBreak())
    story.append(Paragraph("Analysis Notes", styles['Heading2']))
    
    analysis_text = """
    <b>Key Observations:</b><br/>
    <br/>
    1. <b>Prompt Layer Only:</b> These questions represent the baseline output of the prompt engineering layer 
    without any additional refinement layers (context enrichment, semantic validation, quality scoring).<br/>
    <br/>
    2. <b>Expected Improvement Areas:</b><br/>
    • Context Enrichment Layer: Could improve question relevance by selecting better study material chunks<br/>
    • Semantic Validation Layer: Could ensure questions are factually correct and well-formed<br/>
    • Quality Scoring Layer: Could filter out low-quality questions before returning to user<br/>
    <br/>
    3. <b>Consistency Metrics:</b><br/>
    • Question Variety: Assess if questions cover different concepts<br/>
    • Difficulty Alignment: Verify that easy/medium/hard questions match their intended level<br/>
    • Answer Clarity: Check if correct answers are unambiguous<br/>
    <br/>
    4. <b>Next Steps:</b><br/>
    • Implement context enrichment layer to improve material relevance<br/>
    • Add semantic validation to verify question quality<br/>
    • Generate new baseline after implementing each layer for comparison<br/>
    """
    
    story.append(Paragraph(analysis_text, question_style))
    
    # Build PDF
    pdf.build(story)
    print(f"✓ PDF created: {output_path}")


# ============================================================================
# MAIN EXECUTION
# ============================================================================
def main():
    # Configuration
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
    GROQ_MODEL_ID = os.getenv("GROQ_MODEL_ID", "llama-3.3-70b-versatile")
    
    print("=" * 70)
    print("BAYLEARN — BASELINE QUESTION GENERATION ANALYSIS")
    print("=" * 70)
    print()
    
    # Initialize generator
    print("Initializing Groq LLM client...")
    generator = GroqQuestionGenerator(api_key=GROQ_API_KEY, model_id=GROQ_MODEL_ID)
    
    questions_by_difficulty = {}
    
    # Generate questions for each difficulty level
    for difficulty in ['easy', 'medium', 'hard']:
        print(f"\nGenerating 5 {difficulty.upper()} questions...")
        try:
            questions = generator.generate_questions(
                study_material=SAMPLE_STUDY_MATERIAL,
                num_questions=5,
                difficulty=difficulty,
                question_type='mcq'
            )
            questions_by_difficulty[difficulty] = questions
            print(f"✓ Generated {len(questions)} {difficulty} questions")
            
            # Print sample
            if questions:
                print(f"  Sample Q1: {questions[0].get('question_text', '')[:60]}...")
        
        except Exception as e:
            print(f"✗ Error generating {difficulty} questions: {e}")
            questions_by_difficulty[difficulty] = []
    
    # Create PDF report
    print("\n" + "=" * 70)
    print("Creating PDF report...")
    output_pdf = os.path.join(
        os.path.dirname(__file__),
        "baseline_questions_analysis.pdf"
    )
    
    try:
        generate_baseline_pdf(questions_by_difficulty, output_pdf)
        print(f"\n✓ Baseline analysis complete!")
        print(f"  PDF: {output_pdf}")
        print(f"  Total questions: {sum(len(q) for q in questions_by_difficulty.values())}")
    except Exception as e:
        print(f"✗ Error creating PDF: {e}")
        raise


if __name__ == "__main__":
    main()
