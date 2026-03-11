from ragas import evaluate, EvaluationDataset, SingleTurnSample
from ragas.metrics import Faithfulness, ResponseRelevancy, LLMContextPrecisionWithoutReference, LLMContextRecall
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from src.config import MODEL_NAME, OLLAMA_BASE_URL, EMBEDDING_MODEL
import json
import os


class RAGASEvaluator:
    """
    Evaluator using RAGAS 0.4.x framework with local LLMs via Ollama.
    Calculates 4 core RAG metrics: Faithfulness, Relevancy, Context Precision, Context Recall.
    """

    def __init__(self, model_name=MODEL_NAME):
        self.llm = LangchainLLMWrapper(
            OllamaLLM(model=model_name, base_url=OLLAMA_BASE_URL)
        )
        self.embeddings = LangchainEmbeddingsWrapper(
            OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)
        )
        self.metrics = [
            Faithfulness(llm=self.llm),
            ResponseRelevancy(llm=self.llm, embeddings=self.embeddings),
            LLMContextPrecisionWithoutReference(llm=self.llm),
            LLMContextRecall(llm=self.llm),
        ]

    def evaluate_response(self, question, answer, contexts, reference=None):
        """
        Evaluates the quality of a single RAG response using RAGAS metrics.

        Args:
            question: The user's input query / error log.
            answer: The LLM-generated analysis.
            contexts: List of retrieved context strings.
            reference: Optional ground truth answer for reference-based metrics.

        Returns:
            Dict with metric scores (0.0 to 1.0) or None on failure.
        """
        try:
            sample = SingleTurnSample(
                user_input=question,
                response=answer,
                retrieved_contexts=contexts,
                reference=reference or "",
            )
            dataset = EvaluationDataset(samples=[sample])

            result = evaluate(
                dataset=dataset,
                metrics=self.metrics,
            )

            scores = result.to_pandas().iloc[0].to_dict()

            return {
                "faithfulness": round(float(scores.get("faithfulness", 0.0)), 4),
                "relevancy": round(float(scores.get("response_relevancy", 0.0)), 4),
                "context_precision": round(float(scores.get("llm_context_precision_without_reference", 0.0)), 4),
                "context_recall": round(float(scores.get("llm_context_recall", 0.0)), 4),
            }
        except Exception as e:
            print(f"RAGAS evaluation error: {e}")
            return {
                "faithfulness": 0.0,
                "relevancy": 0.0,
                "context_precision": 0.0,
                "context_recall": 0.0,
            }

    def evaluate_dataset(self, dataset_path=None):
        """
        Runs RAGAS evaluation on a full dataset for batch testing.

        Args:
            dataset_path: Path to eval_dataset.json. Defaults to data/eval_dataset.json.

        Returns:
            Dict with per-sample scores and aggregate averages.
        """
        if dataset_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            dataset_path = os.path.join(base_dir, "data", "eval_dataset.json")

        with open(dataset_path, "r", encoding="utf-8") as f:
            test_cases = json.load(f)

        samples = []
        for case in test_cases:
            samples.append(SingleTurnSample(
                user_input=case["question"],
                response=case.get("ground_truth", ""),
                retrieved_contexts=case.get("contexts", []),
                reference=case.get("ground_truth", ""),
            ))

        dataset = EvaluationDataset(samples=samples)

        result = evaluate(
            dataset=dataset,
            metrics=self.metrics,
        )

        df = result.to_pandas()
        per_sample = df.to_dict(orient="records")
        averages = {
            "avg_faithfulness": round(float(df["faithfulness"].mean()), 4),
            "avg_relevancy": round(float(df["response_relevancy"].mean()), 4),
            "avg_context_precision": round(float(df["llm_context_precision_without_reference"].mean()), 4),
            "avg_context_recall": round(float(df["llm_context_recall"].mean()), 4),
        }

        return {
            "per_sample": per_sample,
            "averages": averages,
            "total_samples": len(test_cases),
        }
