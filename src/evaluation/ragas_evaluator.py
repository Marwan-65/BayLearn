import os, json, logging, asyncio, concurrent.futures, numpy as np
from typing import List, Dict, Any
from langchain_community.embeddings import HuggingFaceEmbeddings
logger = logging.getLogger(__name__)
from langchain_groq import ChatGroq 
from .chatgroqfixed import GroqChatFixed  # A custom wrapper to fix OpenAI shim issues in RAGAS

class RAGASEvaluator:
    def __init__(self, groq_api_key: str, timeout: int = 1000):
        self.groq_api_key = groq_api_key
        self.timeout = timeout
        
    def compute_token_stats(before: str, after: str):
        before_tokens = len(before.split())
        after_tokens = len(after.split())

        if before_tokens == 0:
            return {
                "before_tokens": 0,
                "after_tokens": 0,
                "reduction_ratio": 0.0
            }

        reduction = (before_tokens - after_tokens) / before_tokens

        return {
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "reduction_ratio": round(reduction, 3)
        }
    async def evaluate(self, test_cases: List[Dict[str, Any]]) -> Dict[str, float]:
        
        if not test_cases:
            raise ValueError("test_cases cannot be empty")

        for i, case in enumerate(test_cases):
            if isinstance(case.get("contexts"), str):
                test_cases[i]["contexts"] = [case["contexts"]]
            if not isinstance(case.get("contexts"), list):
                test_cases[i]["contexts"] = [""]
            if not case.get("ground_truth"):
                logger.warning(f"Test case {i} missing ground_truth!")
                test_cases[i]["ground_truth"] = ""
            if not case.get("answer", "").strip():
                logger.warning(f"Test case {i} has empty answer!")
        
        def run_ragas():
            from datasets import Dataset
            from ragas import evaluate as ragas_evaluate, run_config
            from ragas.metrics import (
                Faithfulness, AnswerRelevancy,
                ContextPrecision, ContextRecall
            )
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper

            llm = GroqChatFixed(
                model="llama-3.3-70b-versatile",
                groq_api_key=self.groq_api_key,
                temperature=0,
                max_tokens=2048,
                timeout=120.0,
            )

            ragas_llm = LangchainLLMWrapper(llm)

            embeddings = HuggingFaceEmbeddings(
                model_name="BAAI/bge-small-en-v1.5",
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )

            ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)

            dataset = Dataset.from_list(test_cases)

            run_config.timeout = 120.0
            run_config.max_workers = 1
            
            return ragas_evaluate(
                dataset=dataset,
                metrics=[
                    Faithfulness(),
                    AnswerRelevancy(),
                    ContextPrecision(),
                    ContextRecall()
                ],
                llm=ragas_llm,
                embeddings=ragas_embeddings,
                raise_exceptions=True,
            )


        
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, run_ragas)

        return self._extract_scores(results)
    
    def _extract_scores(self, results) -> Dict[str, float]:
        df = results.to_pandas()

        logger.info(f"\n=== Per-row RAGAS scores ===\n{df.to_string()}")

        metrics = ["Faithfulness", "AnswerRelevancy", "ContextPrecision", "ContextRecall"]
        scores = {}

        for metric in metrics:
            if metric in df.columns:
                valid = df[metric].dropna()
                scores[metric] = round(float(valid.mean()), 3) if len(valid) > 0 else 0.0
            else:
                scores[metric] = 0.0

        if "before_tokens" in df.columns and "after_tokens" in df.columns:
            avg_before = df["before_tokens"].mean()
            avg_after = df["after_tokens"].mean()
            reduction = (avg_before - avg_after) / avg_before if avg_before > 0 else 0
            scores["avg_before_tokens"] = round(avg_before, 1)
            scores["avg_after_tokens"] = round(avg_after, 1)
            scores["avg_reduction_ratio"] = round(reduction, 3)

        scores["overall"] = round(float(np.mean(list(scores.values())[:4])), 3)

        logger.info(f"Final scores: {scores}")
        return scores

    def save_results(self, scores, output_path="evaluation_results.json"):
        import datetime
        data = {
            "scores": scores,
            "metadata": {
                "timestamp": datetime.datetime.now().isoformat(),
                "evaluator": "RAGAS (fixed - native Groq)",
                "llm": "llama3-70b-8192 via langchain-groq",
                "embeddings": "BAAI/bge-small-en-v1.5"
            }
        }
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)