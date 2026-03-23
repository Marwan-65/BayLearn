import os, json, logging, asyncio, concurrent.futures, numpy as np
from typing import List, Dict, Any
from langchain_community.embeddings import HuggingFaceEmbeddings
logger = logging.getLogger(__name__)
from langchain_groq import ChatGroq 
from .chatgroqfixed import GroqChatFixed  # A custom wrapper to fix OpenAI shim issues in RAGAS

class RAGASEvaluator:
    def __init__(self, groq_api_key: str, timeout: int = 300):
        self.groq_api_key = groq_api_key
        self.timeout = timeout

    def evaluate(self, test_cases: List[Dict[str, Any]]) -> Dict[str, float]:
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
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from datasets import Dataset
                from ragas import evaluate as ragas_evaluate, run_config
                from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
                from ragas.llms import LangchainLLMWrapper
                from ragas.embeddings import LangchainEmbeddingsWrapper

                # FIX 1: Use native ChatGroq, NOT OpenAI shim
                # The OpenAI shim injects params like 'n=1' that Groq rejects silently
                llm = GroqChatFixed(
                    #model="llama3-70b-8192",
                    model = "llama-3.1-8b-instant",
                    groq_api_key=self.groq_api_key,
                    temperature=0,
                    max_tokens=2048,
                    
                )
                ragas_llm = LangchainLLMWrapper(llm)

                # class LocalEmbeddings(Embeddings):
                #     def __init__(self):
                #         self.model = "sentence-transformers/all-MiniLM-L6-v2"
                #     def embed_documents(self, texts):
                #         return self.model.encode(texts, show_progress_bar=False).tolist()
                #     def embed_query(self, text):
                #         return self.model.encode(text, show_progress_bar=False).tolist()
                # 🔧 UPGRADE: Use BGE embeddings for better performance
                embeddings = HuggingFaceEmbeddings(
                    model_name="BAAI/bge-small-en-v1.5",
                    model_kwargs={'device': 'cpu'},
                    encode_kwargs={'normalize_embeddings': True}
                )
                ragas_embeddings = LangchainEmbeddingsWrapper(embeddings)
                dataset = Dataset.from_list(test_cases)
                run_config.max_workers = 3  # Disable retries to surface issues immediately
                # FIX 2: raise_exceptions=True surfaces silent failures
                results = ragas_evaluate(
                    dataset=dataset,
                    metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
                    llm=ragas_llm,
                    embeddings=ragas_embeddings,
                    raise_exceptions=True,
                )
                return results
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_ragas)
            results = future.result(timeout=self.timeout)
        return self._extract_scores(results)

    def _extract_scores(self, results) -> Dict[str, float]:
        df = results.to_pandas()
        logger.info(f"\n=== Per-row RAGAS scores ===\n{df.to_string()}")
        metrics = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
        scores = {}
        for metric in metrics:
            if metric in df.columns:
                valid = df[metric].dropna()
                scores[metric] = round(float(valid.mean()), 3) if len(valid) > 0 else 0.0
            else:
                scores[metric] = 0.0
        scores["overall"] = round(float(np.mean(list(scores.values()))), 3)
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