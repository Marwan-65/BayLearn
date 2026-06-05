import os, json, logging, asyncio, numpy as np
from typing import List, Dict, Any
logger = logging.getLogger(__name__)
from datasets import Dataset
from ragas import evaluate as ragas_evaluate
from ragas.run_config import RunConfig
from ragas.metrics import (
    Faithfulness, AnswerRelevancy,
    ContextPrecision, ContextRecall,)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import ChatOpenAI
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from .chatgroqfixed import GroqChatFixed


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
            from helpers.config import get_settings
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

    def _run_ragas_openai_compat(self, test_cases):
        model = self.oc_model or "llama-3.3-70b"
        base_url = self.oc_base_url or "https://api.cerebras.ai/v1"
        logger.info(f"RAGAS judge: OpenAI-compatible {model} @ {base_url}")
        llm = ChatOpenAI(
            model=model,
            api_key=self.oc_api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=2048,
            max_retries=10,   # honor free-tier 30 RPM caps with backoff
            timeout=120,
        )
        ragas_llm = LangchainLLMWrapper(llm)
        embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)
        dataset = Dataset.from_list(test_cases)
        cfg = RunConfig(timeout=180, max_retries=12, max_workers=1)
        return ragas_evaluate(
            dataset=dataset,
            metrics=[Faithfulness(), AnswerRelevancy(strictness=1),
                    ContextPrecision(), ContextRecall()],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            run_config=cfg,
            raise_exceptions=False,
        )
    def _run_ragas_gemini(self, test_cases):
        judge_model = os.getenv("RAGAS_JUDGE_MODEL") or os.getenv("GEMINI_MODEL_ID") \
            or "gemini-2.5-flash-lite"
        llm = ChatGoogleGenerativeAI(
            model=judge_model,
            google_api_key=self.gemini_api_key,
            temperature=0,
            max_output_tokens=2048,
            # transport="rest" is REQUIRED for the new AQ.-prefixed AI Studio keys.
            # The default gRPC transport mis-sends the AQ. key as an OAuth bearer
            # token -> 401 "ACCESS_TOKEN_TYPE_UNSUPPORTED". REST sends it via the
            # x-goog-api-key header (same path google-genai uses for generation),
            # which the AQ. key accepts. Legacy AIza keys work on either transport.
            transport="rest",
        )
        ragas_llm = LangchainLLMWrapper(llm)

        embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)

        dataset = Dataset.from_list(test_cases)
        # max_workers=1 -> sequential API calls (avoids rate-limit bursts on free tier).
        # timeout=180   -> per-API-call timeout in seconds.
        # max_retries=12 -> free-tier RPM caps (e.g. ~10 RPM on gemini-2.5-flash-lite)
        #   mean many calls get a transient 429; the langchain client honors the
        #   server's retry_delay, so generous retries let the run self-pace instead
        #   of failing a metric.
        cfg = RunConfig(timeout=180, max_retries=12, max_workers=1)

        # strictness=1 -> AnswerRelevancy generates ONE probe question per answer
        # instead of the default 3. On free-tier judges this cuts the relevancy
        # API-call volume by 3×, which is the single biggest source of the
        # rate-limit budget exhaustion that produced None scores. One probe is
        # enough to compute relevancy; the extra two only reduce variance slightly.
        return ragas_evaluate(
            dataset=dataset,
            metrics=[Faithfulness(), AnswerRelevancy(strictness=1),
                    ContextPrecision(), ContextRecall()],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
            run_config=cfg,
            raise_exceptions=False,
        )
    def _run_ragas_groq(self, test_cases):
        # Groq free 8b tier = 6000 tokens/MINUTE. Each call's request = prompt +
        # max_tokens. At max_tokens=2048 the request was ~3384 tokens -> only ~2
        # calls/min fit and the 3rd 429s. Two mitigations:
        #   (1) max_tokens=900 — RAGAS judge outputs (statements/verdicts) are
        #       short, so this shrinks each request well under the TPM ceiling.
        #   (2) max_retries=15 — a TPM 429 says "retry in ~15s"; patient retries
        #       turn it into a wait, not a failure (no more None cells).
        llm = GroqChatFixed(
            model="llama-3.1-8b-instant",
            groq_api_key=self.groq_api_key,
            temperature=0,
            max_tokens=900,
            timeout=120.0,
            # max_retries=4: enough to wait out a per-MINUTE (TPM) 429 (~15s each),
            # but few enough that a per-DAY (TPD) exhausted key fails fast and the
            # judge rotates to the next provider (Cerebras) instead of hanging on
            # 7-minute TPD retry-after waits.
            max_retries=4,
        )
        ragas_llm = LangchainLLMWrapper(llm)

        embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)

        dataset = Dataset.from_list(test_cases)
        # max_workers=1: PROVEN clean (gave EvalSR=1.0, zero None). Groq free tier
        # throttles CONCURRENT requests, so workers>1 makes each call slow past the
        # timeout -> TimeoutError -> None. Serial is slower (~15min/config) but
        # reliable. timeout=240 gives generous headroom per cell.
        cfg = RunConfig(timeout=240, max_retries=4, max_workers=1)

        return ragas_evaluate(
            dataset=dataset,
            # strictness=1 -> AnswerRelevancy uses 1 probe (Groq forces n=1 anyway),
            # which silences the "1 generations instead of 3" warning and cuts calls.
            metrics=[Faithfulness(), AnswerRelevancy(strictness=1),
                    ContextPrecision(), ContextRecall()],
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
                    # dropna mean (reported score — consistent with prior runs)
                    scores[name] = round(float(valid.mean()), 3) if len(valid) else 0.0
                    if n_none > 0:
                        # honest mean treating None as 0 — stored alongside for audit
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
        scores["none_counts"] = none_counts   # record how many judge failures per metric

        # evaluation success rate (ESR) It is the fraction of (question × metric) cells the judge actually scored. A
        # config that "wins" only because its shorter answers were easier to
        # evaluate (fewer claims -> fewer judge calls -> fewer rate-limit drops)
        # will show a HIGHER success rate,so we can see whether a score
        # gap reflects retrieval quality or merely evaluation stability.
        total_cells = n_rows * len(metric_aliases)
        scored_cells = total_cells - sum(none_counts.values())
        scores["eval_success_rate"] = (
            round(scored_cells / total_cells, 3) if total_cells else 0.0
        )
        scores["n_questions"] = n_rows
        logger.info(f"Final scores: {scores}")

        # document per-question records (question + per-metric score + contexts)
        # this is how we verify whether a low faithfulness is a real failure or noise
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
