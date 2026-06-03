import os, json, logging, asyncio, numpy as np
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class RAGASEvaluator:
    """
    Evaluates RAG quality with RAGAS metrics.
    Supports Gemini (default, free/unlimited) or Groq as evaluator LLM.

    Priority: if GEMINI_API_KEY is set in env → use Gemini.
    Fallback:  use Groq (may hit rate limits on free tier).
    """

    def __init__(self, groq_api_key: str = None, gemini_api_key: str = None, timeout: int = 600):
        self.groq_api_key = groq_api_key
        # Priority: explicit arg → os.environ → pydantic Settings (.env file)
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        if not self.gemini_api_key:
            try:
                from helpers.config import get_settings
                self.gemini_api_key = get_settings().GEMINI_API_KEY
            except Exception:
                pass
        self.timeout = timeout
        self._use_gemini = bool(self.gemini_api_key)

    # ── Public ─────────────────────────────────────────────────────────────

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

        runner = self._run_ragas_gemini if self._use_gemini else self._run_ragas_groq

        try:
            loop = asyncio.get_running_loop()
            results = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: runner(test_cases)),
                timeout=self.timeout,
            )
            return self._extract_scores(results)
        except asyncio.TimeoutError:
            logger.error(f"RAGAS evaluation timed out after {self.timeout}s")
            return self._zero_scores("timeout")
        except Exception as e:
            logger.error(f"RAGAS evaluation failed: {e}")
            return self._zero_scores(str(e))

    # ── Gemini runner ──────────────────────────────────────────────────────

    def _run_ragas_gemini(self, test_cases):
        from datasets import Dataset
        from ragas import evaluate as ragas_evaluate
        from ragas.run_config import RunConfig
        from ragas.metrics import (
            Faithfulness, AnswerRelevancy,
            ContextPrecision, ContextRecall,
        )
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from langchain_google_genai import ChatGoogleGenerativeAI
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            from langchain_community.embeddings import HuggingFaceEmbeddings

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=self.gemini_api_key,
            temperature=0,
            max_output_tokens=2048,
        )
        ragas_llm = LangchainLLMWrapper(llm)

        embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)

        dataset = Dataset.from_list(test_cases)
        # max_workers=1 → sequential API calls (avoids rate-limit bursts on free tier).
        # timeout=120   → per-API-call timeout in seconds.
        cfg = RunConfig(timeout=120, max_retries=3, max_workers=1)

        return ragas_evaluate(
            dataset=dataset,
            metrics=[Faithfulness(), AnswerRelevancy(),
                     ContextPrecision(), ContextRecall()],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            run_config=cfg,
            raise_exceptions=False,
        )

    # ── Groq runner (fallback) ─────────────────────────────────────────────

    def _run_ragas_groq(self, test_cases):
        from datasets import Dataset
        from ragas import evaluate as ragas_evaluate
        from ragas.run_config import RunConfig
        from ragas.metrics import (
            Faithfulness, AnswerRelevancy,
            ContextPrecision, ContextRecall,
        )
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            from langchain_community.embeddings import HuggingFaceEmbeddings
        from .chatgroqfixed import GroqChatFixed

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
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)

        dataset = Dataset.from_list(test_cases)
        cfg = RunConfig(timeout=120, max_retries=3, max_workers=1)

        return ragas_evaluate(
            dataset=dataset,
            metrics=[Faithfulness(), AnswerRelevancy(),
                     ContextPrecision(), ContextRecall()],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            run_config=cfg,
            raise_exceptions=False,
        )

    # ── Score extraction ───────────────────────────────────────────────────

    def _extract_scores(self, results) -> Dict[str, float]:
        df = results.to_pandas()
        logger.info(f"\n=== Per-row RAGAS scores ===\n{df.to_string()}")

        metric_aliases = {
            "Faithfulness":    ["Faithfulness",    "faithfulness"],
            "AnswerRelevancy": ["AnswerRelevancy",  "answer_relevancy"],
            "ContextPrecision":["ContextPrecision", "context_precision"],
            "ContextRecall":   ["ContextRecall",    "context_recall"],
        }
        scores = {}
        for name, aliases in metric_aliases.items():
            for alias in aliases:
                if alias in df.columns:
                    valid = df[alias].dropna()
                    scores[name] = round(float(valid.mean()), 3) if len(valid) else 0.0
                    break
            else:
                logger.warning(f"Metric '{name}' not in columns: {list(df.columns)}")
                scores[name] = 0.0

        scores["overall"] = round(float(np.mean(list(scores.values()))), 3)
        logger.info(f"Final scores: {scores}")
        return scores

    def _zero_scores(self, error: str) -> Dict[str, float]:
        return {
            "Faithfulness": 0.0, "AnswerRelevancy": 0.0,
            "ContextPrecision": 0.0, "ContextRecall": 0.0,
            "overall": 0.0, "error": error,
        }

    def save_results(self, scores, test_details=None, label=None,
                     output_path="evaluation_results.json"):
        import datetime

        evaluator_label = (
            "Gemini gemini-2.5-flash" if self._use_gemini
            else "Groq llama-3.1-8b-instant"
        )
        entry = {
            "label": label or "evaluation",
            "scores": scores,
            "metadata": {
                "timestamp": datetime.datetime.now().isoformat(),
                "evaluator": f"RAGAS via {evaluator_label}",
                "embeddings": "BAAI/bge-small-en-v1.5",
            },
        }
        if test_details:
            entry["test_details"] = test_details

        history = []
        if os.path.exists(output_path):
            try:
                with open(output_path) as f:
                    existing = json.load(f)
                history = [existing] if isinstance(existing, dict) else existing
            except Exception:
                history = []

        history.append(entry)
        with open(output_path, "w") as f:
            json.dump(history, f, indent=2)
