import asyncio
import time
import pandas as pd
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from pydantic import BaseModel, Field

from app.services.question_service import QuestionGenerationService
from app.services.context_enrichment import ContextEnrichmentLayer
from app.services.semantic_validator import SemanticValidator, ValidationReport, ValidatorResult
from app.classifier.bloom_classifier import bloom6_to_level
from app.models.schemas import GeneratedQuestion

# ==========================================
# 1. Strict Logging Schema
# ==========================================
class AblationRecord(BaseModel):
    # Meta
    trial_id: str
    condition: str = Field(description="A (Baseline), B (+Enrichment), or C (+Validator)")
    topic: str
    difficulty: str
    question_type: str
    
    question_text: str = ""
    
    # Reliability & Performance
    latency_seconds: float
    parse_success: bool
    empty_output: bool
    validation_retries_used: int
    
    # Alignment (BloomBERT)
    predicted_level: Optional[str] = None
    level_match: Optional[bool] = None
    level_confidence: Optional[float] = None
    
    # Enrichment Diagnostics (Null for Cond A)
    queries_fired: int = 1
    total_retrieved: int = 0
    unique_after_dedup: int = 0
    selected_by_mmr: int = 0
    avg_relevance_score: float = 0.0
    
    # Validator Proxies (Even if bypassed, what *would* it score?)
    # Note: For strict rigor, you might want to run the validator in "shadow mode" 
    # for Cond A and B just to log what it would have caught.
    validator_decision: str = "pass"
    validator_overall_score: float = 1.0
    validator_failure_count: int = 0
    failed_validators: str = "" # Comma separated list of V1, V2 etc.

# ==========================================
# 2. Bypasses (Mocks) for Layer Toggling
# ==========================================
class MockContextEnrichmentLayer:
    """Baseline retrieval: Single query, top-N, no MMR or multi-query."""
    def __init__(self, chunk_fetcher):
        self.chunk_fetcher = chunk_fetcher
        
    async def get_chunks(self, project_id: str, difficulty: str, topic: Optional[str], n: int = 10):
        # Fire a single baseline query
        query = topic if topic else f"{difficulty} concepts"
        chunks = await self.chunk_fetcher.fetch_relevant_chunks(
            project_id=project_id, query=query, limit=n
        )
        # Dummy diagnostics matching the baseline behavior
        diagnostics = {
            "difficulty": difficulty,
            "queries_fired": 1,
            "chunks_per_query": [len(chunks)],
            "total_retrieved": len(chunks),
            "unique_after_dedup": len(chunks),
            "selected_by_mmr": len(chunks),
            "avg_relevance_score": 0.0, # Baseline doesn't calculate this aggressively
        }
        return chunks[:n], diagnostics

class MockSemanticValidator:
    """Baseline validation: Accept everything immediately (zero latency/retries)."""
    def validate_all(self, questions: List[GeneratedQuestion], chunk_texts: List[str]) -> List[ValidationReport]:
        reports = []
        for q in questions:
            # Return a flawless pass report to bypass the rejection loop
            rep = ValidationReport(
                question_text=q.question_text,
                difficulty=q.difficulty,
                decision="pass",
                failure_count=0,
                overall_score=1.0,
                results=[ValidatorResult("V0", "Mock", 1.0, True, "Mock Pass")]
            )
            reports.append(rep)
        return reports

# ==========================================
# 3. The Central Orchestrator
# ==========================================
class AblationHarness:
    def __init__(self, llm_client, chunk_fetcher, example_bank, bloom_classifier, project_id: str):
        self.llm_client = llm_client
        self.chunk_fetcher = chunk_fetcher
        self.example_bank = example_bank
        self.bloom_classifier = bloom_classifier
        self.project_id = project_id
        self.records: List[AblationRecord] = []
        
        # We also keep a "shadow" validator to grade Cond A and B outputs silently
        self.shadow_validator = SemanticValidator()

    def _configure_service(self, condition: str) -> QuestionGenerationService:
        """Injects the correct layers based on the ablation condition."""
        service = QuestionGenerationService(
            llm_client=self.llm_client,
            chunk_fetcher=self.chunk_fetcher,
            example_bank=None,  # 100% Disable ICL to isolate the other layers
            bloom_classifier=self.bloom_classifier,
            few_shot_k=0,       # 100% Disable ICL
            retry_on_level_mismatch=(condition == "C") # Only enable rejection loop for Cond C
        )
        
        if condition == "A":
            # Baseline: No MMR Enrichment, No Rejection Loop
            service.context_enricher = MockContextEnrichmentLayer(self.chunk_fetcher)
            service.validator = MockSemanticValidator()
        elif condition == "B":
            # Enrichment Only: Real MMR, No Rejection Loop
            service.validator = MockSemanticValidator()
        elif condition == "C":
            # Full Pipeline (Leaves the default instantiations intact)
            pass 
            
        return service

    async def run_trial(self, trial_id: str, condition: str, topic: str, difficulty: str, q_type: str):
        service = self._configure_service(condition)
        
        start_time = time.time()
        parse_success = True
        empty_output = False
        questions = []
        
        try:
            questions, _ = await service.generate(
                project_id=self.project_id,
                difficulty=difficulty,
                question_type=q_type,
                topic=topic
            )
            if not questions:
                empty_output = True
        except Exception as e:
            parse_success = False
            
        latency = time.time() - start_time
        
        # Build base record
        record = AblationRecord(
            trial_id=trial_id,
            condition=condition,
            topic=topic,
            difficulty=difficulty,
            question_type=q_type,
            latency_seconds=latency,
            parse_success=parse_success,
            empty_output=empty_output,
            validation_retries_used=0 # Will update below if C
        )

        if questions:
            q = questions[0]
            record.question_text = q.question_text
            
            # 1. Bloom Alignment
            record.predicted_level = q.predicted_level
            record.level_match = (q.predicted_level == bloom6_to_level(difficulty))
            record.level_confidence = q.level_confidence
            
            # 2. Extract Enrichment Diagnostics from the logs/service state if possible
            # (In a real run, you might want to attach diagnostics to the generated question object temporarily)
            
            # 3. Shadow Validation for A and B, Real Validation for C
            if condition in ["A", "B"]:
                # Run the validator silently just to record what it *would* have scored
                shadow_report = self.shadow_validator.validate_all([q], ["dummy text chunk"])[0] 
                
                record.validator_decision = shadow_report.decision
                record.validator_overall_score = shadow_report.overall_score
                record.validator_failure_count = shadow_report.failure_count
                record.failed_validators = ",".join([r.validator for r in shadow_report.results if not r.passed])
            else:
                rep = getattr(q, "validation_report", {}) or {}
                if hasattr(rep, "decision"):
                    record.validator_decision = rep.decision
                    record.validator_overall_score = rep.overall_score
                    record.validator_failure_count = rep.failure_count
                    res = getattr(rep, "results", getattr(rep, "validators", []))
                    record.failed_validators = ",".join([getattr(r, "validator", "") for r in res if not getattr(r, "passed", True)])
                elif isinstance(rep, dict):
                    record.validator_decision = rep.get("decision", "pass")
                    record.validator_overall_score = rep.get("overall_score", 1.0)
                    record.validator_failure_count = rep.get("failure_count", 0)
                    res = rep.get("results", rep.get("validators", []))
                    record.failed_validators = ",".join([r.get("validator", "") for r in res if isinstance(r, dict) and not r.get("passed", True)])
            
        self.records.append(record)
        return record

    def export_results(self, filepath: str = "ablation_results.csv"):
        df = pd.DataFrame([r.model_dump() for r in self.records])
        df.to_csv(filepath, index=False)
        print(f"Exported {len(self.records)} trials to {filepath}")