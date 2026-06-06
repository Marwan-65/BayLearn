import os, json, logging, asyncio, numpy as np
from typing import List, Dict, Any
logger = logging.getLogger(__name__)
from datasets import Dataset
from ragas import evaluate as ragas_evaluate
from ragas.run_config import RunConfig
from ragas.metrics import (
    Faithfulness, AnswerRelevancy,
    ContextPrecision, ContextRecall,)
from helpers.config import get_settings
from RAG_module_models.ragas_judges import (
    build_embeddings,
    build_openai_compat_judge,
    build_gemini_judge,
    build_groq_judge,
)


class RAGASEvaluator:
    def __init__(self, groq_api_key: str = None, gemini_api_key: str = None,
                openai_compat_api_key: str = None, openai_compat_base_url: str = None,
                openai_compat_model: str = None, timeout: int = 600):
        self.groq_api_key = groq_api_key
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.oc_api_key = openai_compat_api_key
        self.oc_base_url = openai_compat_base_url
        self.oc_model = openai_compat_model
        try:
            s = get_settings()
            if not self.gemini_api_key:
                self.gemini_api_key = s.GEMINI_API_KEY
            if not self.oc_api_key:
                self.oc_api_key = getattr(s, "OPENAI_COMPAT_API_KEY", None)
            self.oc_base_url = self.oc_base_url or getattr(s, "OPENAI_COMPAT_BASE_URL", None)
            self.oc_model = self.oc_model or getattr(s, "OPENAI_COMPAT_MODEL", None)
        except Exception:
            pass
        self.timeout = timeout
        self.last_per_question = []  
        self._use_openai_compat = bool(self.oc_api_key)
        self._use_gemini = (not self._use_openai_compat) and bool(self.gemini_api_key)

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

        if self._use_openai_compat:
            runner = self._run_ragas_openai_compat
        elif self._use_gemini:
            runner = self._run_ragas_gemini
        else:
            runner = self._run_ragas_groq

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

    def _metrics(self):
        return [Faithfulness(), AnswerRelevancy(strictness=1),
                ContextPrecision(), ContextRecall()]

    def _run_ragas_openai_compat(self, test_cases):
        logger.info(f"RAGAS judge: OpenAI-compatible {self.oc_model or 'default'}")
        ragas_llm = build_openai_compat_judge(self.oc_api_key, self.oc_base_url, self.oc_model)
        ragas_embeddings = build_embeddings()
        dataset = Dataset.from_list(test_cases)
        cfg = RunConfig(timeout=180, max_retries=12, max_workers=1)
        return ragas_evaluate(
            dataset=dataset,
            metrics=self._metrics(),
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            run_config=cfg,
            raise_exceptions=False,
        )

    def _run_ragas_gemini(self, test_cases):
        judge_model = os.getenv("RAGAS_JUDGE_MODEL") or os.getenv("GEMINI_MODEL_ID") \
            or "gemini-2.5-flash-lite"
        ragas_llm = build_gemini_judge(self.gemini_api_key, judge_model)
        ragas_embeddings = build_embeddings()
        dataset = Dataset.from_list(test_cases)
        cfg = RunConfig(timeout=180, max_retries=12, max_workers=1)
        return ragas_evaluate(
            dataset=dataset,
            metrics=self._metrics(),
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            run_config=cfg,
            raise_exceptions=False,
        )

    def _run_ragas_groq(self, test_cases):
        ragas_llm = build_groq_judge(self.groq_api_key)
        ragas_embeddings = build_embeddings()
        dataset = Dataset.from_list(test_cases)
        cfg = RunConfig(timeout=240, max_retries=4, max_workers=1)
        return ragas_evaluate(
            dataset=dataset,
            metrics=self._metrics(),
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            run_config=cfg,
            raise_exceptions=False,
        )
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
        none_counts = {}
        n_rows = len(df)
        for name, aliases in metric_aliases.items():
            for alias in aliases:
                if alias in df.columns:
                    col_data = df[alias]
                    valid = col_data.dropna()
                    n_none = n_rows - len(valid)
                    none_counts[name] = n_none
                    # dropna mean (reported score, consistent with prior runs)
                    scores[name] = round(float(valid.mean()), 3) if len(valid) else 0.0
                    if n_none > 0:
                        # honest mean treating None as 0, stored alongside for audit
                        full_mean = round(float(col_data.fillna(0).mean()), 3)
                        logger.warning(
                            f"Metric '{name}': {n_none}/{n_rows} questions returned None "
                            f"(RAGAS judge failure). dropna avg={scores[name]:.3f}, "
                            f"honest avg (None=0)={full_mean:.3f}. "
                            f"Reported score uses dropna — may be inflated."
                        )
                    break
            else:
                logger.warning(f"Metric '{name}' not in columns: {list(df.columns)}")
                scores[name] = 0.0
                none_counts[name] = n_rows

        metric_vals = [scores[m] for m in metric_aliases if m in scores]
        scores["overall"] = round(float(np.mean(metric_vals)), 3)
        scores["none_counts"] = none_counts  
        total_cells = n_rows * len(metric_aliases)
        scored_cells = total_cells - sum(none_counts.values())
        scores["eval_success_rate"] = (
            round(scored_cells / total_cells, 3) if total_cells else 0.0
        )
        scores["n_questions"] = n_rows
        logger.info(f"Final scores: {scores}")
        try:
            col = {}
            for name, aliases in metric_aliases.items():
                for a in aliases:
                    if a in df.columns:
                        col[name] = a; break
            qcol = "user_input" if "user_input" in df.columns else (
                "question" if "question" in df.columns else None)
            per_q = []
            for _, row in df.iterrows():
                rec = {"question": (str(row[qcol])[:200] if qcol else None)}
                for name, a in col.items():
                    v = row.get(a)
                    rec[name] = (None if v is None or (isinstance(v, float) and v != v)
                        else round(float(v), 3))
                per_q.append(rec)
            self.last_per_question = per_q
        except Exception as e:
            logger.warning(f"Could not build per-question records: {e}")
            self.last_per_question = []
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
