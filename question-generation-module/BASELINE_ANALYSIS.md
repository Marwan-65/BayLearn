# BayLearn Question Generation — Baseline Analysis Report

**Generated:** 2026-05-24  
**Status:** Baseline (Prompt Layer Only)  
**Total Questions:** 15 (5 Easy, 5 Medium, 5 Hard)

---

## Executive Summary

This document establishes the **baseline** for question generation quality using **only the prompt layer** (no improvement layers). The baseline consists of 15 multiple-choice questions generated from uniform study material (Physics fundamentals) using the Groq LLM.

### Key Purpose
- **Establish reference point** for question quality before adding improvement layers
- **Measure impact** of future enhancements (context enrichment, semantic validation, quality scoring)
- **Identify current limitations** that layers will address
- **Track progression** as each layer is implemented

---

## Current Architecture (Baseline)

### Flow
```
Study Material
    ↓
Prompt Engineering (System + User Prompt)
    ↓
Groq LLM (llama-3.3-70b-versatile)
    ↓
JSON Parsing
    ↓
Questions Output
```

### Configuration
- **LLM Model:** llama-3.3-70b-versatile
- **Temperature:** 0.85 (high creativity for diversity)
- **Max Tokens:** 2000+ (increased to avoid truncation)
- **Study Material:** Physics (Newton's Laws, Kinematics, Energy, Momentum, Gravity)
- **Question Type:** Multiple Choice (MCQ)

---

## Baseline Findings

### Current Strengths (What Works Well)
1. ✅ **Question Generation Speed** - Fast turnaround (single LLM call)
2. ✅ **Format Consistency** - Returns valid JSON structure
3. ✅ **Difficulty Distinction** - Questions clearly differ by level
4. ✅ **Basic Coverage** - Touches on different topics from material

### Current Limitations (What Needs Improvement)

#### 1. **Context Quality Issues**
- **Problem:** All questions from same uniform chunk
- **Impact:** Limited content diversity, may miss important topics
- **Solution:** Context Enrichment Layer
  - Intelligent chunk selection based on question type
  - Multi-pass retrieval focusing on different aspects
  - Semantic diversity scoring

#### 2. **Semantic Validation Issues**
- **Problem:** No verification of question correctness
- **Impact:** May include technically incorrect content
- **Solution:** Semantic Validation Layer
  - Cross-reference facts against source material
  - Verify mathematical correctness
  - Check for ambiguous or trick questions

#### 3. **Quality Filtering Issues**
- **Problem:** No quality scoring before returning
- **Impact:** Users receive inconsistent quality questions
- **Solution:** Quality Scoring Layer
  - Evaluate question clarity and difficulty alignment
  - Score options for distinctiveness
  - Filter out ambiguous explanations

#### 4. **Explainability Issues**
- **Problem:** No insight into generation reasoning
- **Impact:** Hard to improve or debug generation
- **Solution:** Annotation Layer
  - Add confidence scores
  - Include generation metadata
  - Highlight key concepts covered

---

## Planned Improvement Layers

### Layer 1: Context Enrichment (Next Priority)
**Goal:** Select better study material chunks for question generation

**Approach:**
- Analyze question requirements before chunk selection
- Use semantic similarity to find diverse relevant chunks
- Score chunks by relevance and diversity
- Feed top chunks to prompt

**Expected Impact:**
- 30-40% improvement in content relevance
- Better coverage of material
- More contextually appropriate questions

### Layer 2: Semantic Validation
**Goal:** Verify questions are factually correct

**Approach:**
- Extract key claims from questions and answers
- Validate against source material
- Check mathematical correctness
- Verify answer uniqueness

**Expected Impact:**
- Eliminate factually incorrect questions
- Improve explanation quality
- Ensure answer correctness

### Layer 3: Quality Scoring
**Goal:** Filter and rank questions by quality

**Approach:**
- Score clarity of question text
- Score distinctiveness of wrong answers
- Score alignment with stated difficulty
- Score explanation completeness

**Expected Impact:**
- Remove low-quality questions
- Ensure difficulty consistency
- Improve user satisfaction

### Layer 4: Annotation & Metadata
**Goal:** Add generation insights

**Approach:**
- Record source chunks used
- Include confidence scores
- Tag key concepts covered
- Note generation rationale

**Expected Impact:**
- Better traceability
- Improved debugging
- Rich metadata for analytics

---

## Baseline Questions (Summary)

### Easy Questions (5)
- Basic definition and recall questions
- Direct facts from material
- Example: "What is inertia according to Newton's First Law?"

### Medium Questions (5)
- Application and explanation questions
- Require connecting concepts
- Example: "Apply Newton's Second Law to find acceleration..."

### Hard Questions (5)
- Analysis and synthesis questions
- Require critical thinking
- Example: "Analyze the relationship between force, mass, and acceleration..."

---

## Files Generated

1. **baseline_questions_analysis.pdf** (11 KB)
   - Formatted PDF with all 15 questions
   - Color-coded by difficulty
   - Includes explanations

2. **baseline_questions.json**
   - Machine-readable format
   - Metadata included
   - Ready for analysis scripts

3. **This Document**
   - Analysis and recommendations
   - Architecture overview
   - Layer descriptions

---

## Next Steps

### Immediate Actions
1. ✅ Baseline established (current state)
2. ⏭️ Implement Context Enrichment Layer
3. ⏭️ Run questions through enriched layer
4. ⏭️ Compare results to baseline

### Success Metrics (Per Layer)
- **Content Relevance:** Measure concept coverage improvement
- **Factual Accuracy:** Count errors in baseline vs. layer
- **User Satisfaction:** Score question quality
- **Performance:** Track generation time

### Testing Strategy
- Generate 15 questions per layer (same topic)
- Compare against baseline
- Analyze improvement metrics
- Document findings in checkpoint

---

## Technical Notes

### Groq Model Configuration
- **Model ID:** llama-3.3-70b-versatile
- **API Key:** Set via GROQ_API_KEY environment variable
- **Base URL:** Groq API (configured in groq_client.py)

### Reproducibility
- Same study material used for all tests
- Temperature fixed at 0.85 for consistency
- JSON parsing with error handling

### Known Limitations
- Single LLM provider (Groq) — no model comparison yet
- Fixed temperature — could explore varying by difficulty
- No feedback loop — questions not refined based on usage

---

## Conclusion

The baseline establishes a functional baseline using prompt engineering alone. Each improvement layer will address specific weaknesses:
- **Context:** Better material selection
- **Validation:** Correctness checking
- **Scoring:** Quality filtering
- **Metadata:** Explainability

This phased approach allows measuring the impact of each layer independently.
