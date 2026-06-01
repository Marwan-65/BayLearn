import os, json, logging, asyncio, numpy as np
from typing import List, Dict, Any
from langchain_community.embeddings import HuggingFaceEmbeddings
logger = logging.getLogger(__name__)
from langchain_groq import ChatGroq 
from .chatgroqfixed import GroqChatFixed  # A custom wrapper to fix OpenAI shim issues in RAGAS

class RAGASEvaluator:
    def __init__(self, groq_api_key: str, timeout: int = 600):
        self.groq_api_key = groq_api_key
        self.timeout = timeout

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
                model="llama-3.1-8b-instant",
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

            run_config.timeout = 300.0
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
                raise_exceptions=False,
            )

        try:
            loop = asyncio.get_running_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(None, run_ragas),
                timeout=self.timeout
            )
            return self._extract_scores(results)
        except TimeoutError:
            logger.error(f"RAGAS evaluation timed out after {self.timeout}s")
            return {
                "Faithfulness": 0.0, "AnswerRelevancy": 0.0,
                "ContextPrecision": 0.0, "ContextRecall": 0.0,
                "overall": 0.0, "error": "timeout"
            }
        except Exception as e:
            logger.error(f"RAGAS evaluation failed: {e}")
            return {
                "Faithfulness": 0.0, "AnswerRelevancy": 0.0,
                "ContextPrecision": 0.0, "ContextRecall": 0.0,
                "overall": 0.0, "error": str(e)
            }
        
    def _extract_scores(self, results) -> Dict[str, float]:
        df = results.to_pandas()
        logger.info(f"\n=== Per-row RAGAS scores ===\n{df.to_string()}")
        logger.info(f"RAGAS DataFrame columns: {list(df.columns)}")

        # Map both PascalCase and snake_case column names (varies by RAGAS version)
        metric_aliases = {
            "Faithfulness": ["Faithfulness", "faithfulness"],
            "AnswerRelevancy": ["AnswerRelevancy", "answer_relevancy"],
            "ContextPrecision": ["ContextPrecision", "context_precision"],
            "ContextRecall": ["ContextRecall", "context_recall"],
        }

        scores = {}
        for metric_name, aliases in metric_aliases.items():
            found = False
            for alias in aliases:
                if alias in df.columns:
                    valid = df[alias].dropna()
                    scores[metric_name] = round(float(valid.mean()), 3) if len(valid) > 0 else 0.0
                    found = True
                    break
            if not found:
                logger.warning(f"Metric '{metric_name}' not found in columns: {list(df.columns)}")
                scores[metric_name] = 0.0

        scores["overall"] = round(float(np.mean(list(scores.values()))), 3)
        logger.info(f"Final scores: {scores}")
        return scores

    def save_results(self, scores, test_details=None, label=None,
                     output_path="evaluation_results.json"):
        import datetime

        entry = {
            "label": label or "evaluation",
            "scores": scores,
            "metadata": {
                "timestamp": datetime.datetime.now().isoformat(),
                "evaluator": "RAGAS (fixed - native Groq)",
                "llm": "llama3-70b-8192 via langchain-groq",
                "embeddings": "BAAI/bge-small-en-v1.5"
            },
        }
        if test_details:
            entry["test_details"] = test_details

        # Append mode — preserve evaluation history for thesis comparison
        history = []
        if os.path.exists(output_path):
            try:
                with open(output_path, "r") as f:
                    existing = json.load(f)
                # Handle old format (single dict) by wrapping in list
                if isinstance(existing, dict):
                    history = [existing]
                elif isinstance(existing, list):
                    history = existing
            except (json.JSONDecodeError, Exception):
                history = []

        history.append(entry)
        with open(output_path, "w") as f:
            json.dump(history, f, indent=2)