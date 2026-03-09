from langchain_ollama import OllamaLLM
from src.config import MODEL_NAME

# NOTE: Real RAGAS evaluation requires an OpenAI-compatible LLM or a mapped local LLM.
# The evaluate() call below is the intended production path; it is currently commented out
# until a compatible LLM wrapper is configured. The fallback returns heuristic-based
# scores derived from context overlap instead of random numbers.

class RAGASEvaluator:
    def __init__(self, model_name=MODEL_NAME):
        self.llm = OllamaLLM(model=model_name)

    def evaluate_response(self, question, answer, contexts):
        """
        Evaluates the quality of a single RAG response.

        Production path (uncomment when a RAGAS-compatible LLM wrapper is set up):
            from ragas import evaluate
            from ragas.metrics import faithfulness, answer_relevancy
            from datasets import Dataset
            data = Dataset.from_dict({
                "question": [question],
                "answer": [answer],
                "contexts": [contexts],
            })
            result = evaluate(data, metrics=[faithfulness, answer_relevancy], llm=...)
            return {"faithfulness": result["faithfulness"], "relevancy": result["answer_relevancy"]}

        Until then, a lightweight heuristic approximation is used.
        """
        try:
            combined_context = " ".join(contexts).lower()
            answer_lower = answer.lower()
            question_lower = question.lower()

            # Faithfulness: fraction of answer tokens found in context
            answer_tokens = set(answer_lower.split())
            context_tokens = set(combined_context.split())
            faithfulness = len(answer_tokens & context_tokens) / max(len(answer_tokens), 1)
            faithfulness = round(min(max(faithfulness, 0.0), 1.0), 2)

            # Relevancy: fraction of question tokens covered by the answer
            question_tokens = set(question_lower.split())
            relevancy = len(question_tokens & answer_tokens) / max(len(question_tokens), 1)
            relevancy = round(min(max(relevancy, 0.0), 1.0), 2)

            return {"faithfulness": faithfulness, "relevancy": relevancy}
        except Exception as e:
            print(f"Evaluation error: {e}")
            return None
