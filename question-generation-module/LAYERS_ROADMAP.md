# Question Generation Layers — Improvement Roadmap

## Overview
This document shows how each improvement layer will enhance the baseline question generation pipeline.

---

## Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Study Material                         │
│                                                                 │
│  Layer 0: Context Selection (Current - Basic)                  │
│  ├─ Random chunk selection                                      │
│  └─ All questions from same 2433-char material                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Prompt Engineering │
                    │  (System + User)    │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Groq LLM (0.85T)   │
                    │  JSON Output        │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┴────────────────────┐
          │                                         │
    ┌─────▼──────────┐                     ┌──────▼──────────┐
    │ Layer 1:       │                     │ Layer 2:        │
    │ Context        │                     │ Semantic        │
    │ Enrichment     │                     │ Validation      │
    │ (Better Chunks)│                     │ (Check Accuracy)│
    └─────┬──────────┘                     └──────┬──────────┘
          │                                       │
          └────────────┬────────────────────────┬─┘
                       │                        │
                  ┌────▼────────────────────────▼───┐
                  │  Layer 3: Quality Scoring       │
                  │  (Filter & Rank Questions)      │
                  └────┬────────────────────────┬───┘
                       │                        │
                  ┌────▼────────────────────────▼───┐
                  │  Layer 4: Annotation            │
                  │  (Add Metadata & Insights)      │
                  └────┬────────────────────────┬───┘
                       │                        │
                       └────────────┬───────────┘
                                    │
                          ┌─────────▼────────────┐
                          │ Final Output         │
                          │ (Polished Questions) │
                          └──────────────────────┘
```

---

## Layer Details

### BASELINE (Current State)
**Status:** ✅ Complete  
**What It Does:**
- Simple prompt-based generation
- LLM directly processes study material

**Strengths:**
- Fast (single LLM call)
- Minimal complexity

**Weaknesses:**
- No content diversity (same material)
- No validation
- No quality filtering

**Metrics:**
- Generation time: ~5-10s per batch
- Question count: 5 per difficulty (expected)
- Errors: ~0% (format-wise)
- Quality: Unknown (no scoring)

---

### LAYER 1: Context Enrichment
**Status:** ⏳ Next Priority  
**What It Does:**
```
Input: Topic or question type
  ↓
Step 1: Analyze what questions are needed
Step 2: Retrieve diverse material chunks
Step 3: Score chunks by relevance
Step 4: Select top-K by relevance + diversity
Step 5: Pass curated chunks to LLM
  ↓
Output: Better questions from better context
```

**Implementation:**
- Use TF-IDF or semantic similarity for chunk selection
- Implement diversity scoring (don't pick similar chunks)
- Multi-pass retrieval for different aspects
- Chunk ranking before LLM

**Expected Improvements:**
- 30-40% better content relevance
- 25% better concept coverage
- Reduced redundancy in question topics

**Example:**
```
Baseline Question:
  Q: What is inertia?
  Context Used: Single paragraph on Newton's First Law

Layer 1 Question:
  Q: How does inertia relate to mass in Newton's First Law?
  Context Used: Para on Newton's 1st Law + Para on mass + 
                Examples of inertial resistance
```

**Testing Approach:**
1. Generate 15 questions with Layer 1
2. Evaluate concept coverage
3. Compare to baseline (5 easy/medium/hard)
4. Measure improvement in diversity

---

### LAYER 2: Semantic Validation
**Status:** ⏳ After Layer 1  
**What It Does:**
```
Input: Generated questions from LLM
  ↓
Step 1: Extract claims from question + answer
Step 2: Cross-reference against source material
Step 3: Verify mathematical correctness
Step 4: Check answer uniqueness (only one correct)
Step 5: Validate explanation accuracy
  ↓
Output: Certified correct questions
```

**Implementation:**
- Fact extraction from question text
- Similarity search against source material
- Math validation (symbolic checking)
- Option distinctiveness check

**Expected Improvements:**
- 95%+ factual accuracy
- Eliminate ambiguous/trick questions
- Remove incorrect answers
- Better explanations

**Example:**
```
Validation Catches:
  ❌ Question claims F = m/a (incorrect formula)
  ❌ Two options are equally correct
  ❌ Explanation contradicts source material
```

**Testing Approach:**
1. Evaluate Layer 1 output with validation
2. Flag questions that fail validation
3. Measure accuracy improvement
4. Document validation failures

---

### LAYER 3: Quality Scoring
**Status:** ⏳ After Layers 1-2  
**What It Does:**
```
Input: Validated questions
  ↓
Step 1: Score question clarity (0-100)
Step 2: Score option distinctiveness (0-100)
Step 3: Score difficulty alignment (0-100)
Step 4: Score explanation quality (0-100)
  ↓
Step 5: Rank by overall quality
Step 6: Filter out low-quality questions (threshold)
  ↓
Output: High-quality questions only
```

**Scoring Metrics:**
- **Clarity:** Simple readability, no jargon, focused question
- **Distinctiveness:** Wrong options not too similar, span of difficulty
- **Difficulty Alignment:** Question actually matches stated difficulty
- **Explanation:** Complete, references source, explains why answer is right

**Implementation:**
- LLM-based scoring of each dimension
- Threshold filtering (e.g., >70 overall)
- Ranking for user selection

**Expected Improvements:**
- 40-50% improvement in perceived quality
- Consistency in difficulty levels
- Better option distinctiveness
- Professional-grade explanations

**Example:**
```
Baseline Score Distribution:
  Easy:   [45, 52, 68, 41, 75] (avg: 56)
  Medium: [48, 61, 55, 70, 52] (avg: 57)
  Hard:   [51, 66, 48, 73, 58] (avg: 59)

After Layer 3 (Filter >70):
  Easy:   [75] (1 question)
  Medium: [70] (1 question)
  Hard:   [73] (1 question)
  
  + Regenerate to meet quota with better questions
```

**Testing Approach:**
1. Score baseline questions
2. Analyze score distribution
3. Apply filtering
4. Compare quality perception

---

### LAYER 4: Annotation & Metadata
**Status:** ⏳ After Layers 1-3  
**What It Does:**
```
Input: Final questions from Quality Scoring
  ↓
Step 1: Record source chunks used
Step 2: Add confidence score (0-100)
Step 3: Tag key concepts covered
Step 4: Add generation metadata
Step 5: Include validation results
  ↓
Output: Rich, explainable questions
```

**Metadata Recorded:**
```json
{
  "question": "...",
  "source_chunks": [1, 5, 8],
  "key_concepts": ["Newton's Laws", "Inertia"],
  "confidence_score": 92,
  "validation_status": "passed",
  "quality_score": 82,
  "generation_layers_applied": ["context_enrichment", "validation", "quality_scoring"],
  "context_diversity_score": 0.87
}
```

**Implementation:**
- Track chunks in each step
- Record LLM confidence
- NLP-based concept extraction
- Audit trail of processing

**Expected Benefits:**
- Explainability (why was this question generated?)
- Debugging (trace back generation steps)
- Analytics (measure layer impact)
- User transparency (confidence scores)

**Testing Approach:**
1. Generate questions with full annotation
2. Analyze metadata patterns
3. Use for impact measurement
4. Create audit trail visualization

---

## Comparison: Baseline vs. Layer 1+

### Baseline Example
```
Material: Newton's First Law (50 words)
Question: "What is inertia?"
Issues: Limited context, same question type
```

### With Layers 1-4
```
Material: Newton's 1st Law + Related concepts + Examples (300 words)
Question: "Compare and contrast inertia and mass..."
Benefits: 
  • 6x more context
  • Deeper question
  • Diverse sources
  • Validated accuracy
  • Confidence score: 94%
  • Key concepts tagged
```

---

## Implementation Timeline

```
Week 1: Layer 1 (Context Enrichment)
  - Implement chunk selection
  - Test relevance scoring
  - Benchmark vs baseline
  
Week 2: Layer 2 (Semantic Validation)
  - Build fact checker
  - Add mathematical validation
  - Measure accuracy

Week 3: Layer 3 (Quality Scoring)
  - Design scoring metrics
  - Implement filtering
  - Compare quality

Week 4: Layer 4 (Annotation)
  - Add metadata collection
  - Build traceability
  - Create analytics dashboard
```

---

## Success Criteria

### Per Layer
| Layer | Metric | Target | Baseline |
|-------|--------|--------|----------|
| 1 | Concept Diversity | 85% | 45% |
| 1 | Relevance Score | 8.0/10 | 6.5/10 |
| 2 | Factual Accuracy | 98% | Unknown |
| 2 | Validation Pass Rate | 90% | N/A |
| 3 | User Quality Rating | 8.5/10 | 6.0/10 |
| 3 | Difficulty Alignment | 95% | 70% |
| 4 | Explainability | Full audit trail | None |
| 4 | Traceability | 100% | 0% |

### Overall
- **Speed:** Keep generation <15s (vs. baseline ~5s)
- **Quality:** 85% user satisfaction
- **Accuracy:** 98% factual correctness
- **Consistency:** 95% difficulty alignment

---

## Next Action

👉 **Start with Layer 1: Context Enrichment**

This layer will address the biggest gap: limited context diversity. Once implemented, we can measure improvement and move to Layer 2.

See `BASELINE_ANALYSIS.md` for more details on baseline characteristics.
