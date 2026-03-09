import re
import json
from langchain_ollama import OllamaLLM
from src.config import MODEL_NAME

_JUDGE_PROMPT = """You are an expert QA evaluator assessing the quality of an AI-generated debugging analysis.

Question: {question}

Answer given: {answer}

Context that was available: {context}

Evaluate strictly on a scale from 0.0 to 1.0:
- faithfulness: Is EVERY factual claim in the answer directly supported by the context?
  (1.0 = fully grounded, 0.0 = completely hallucinated)
- relevancy: Does the answer directly and completely address the question?
  (1.0 = perfectly on-topic, 0.0 = irrelevant)

Return ONLY a JSON object with no extra text:
{{"faithfulness": X.X, "relevancy": X.X}}"""


class RAGASEvaluator:
    def __init__(self, model_name=MODEL_NAME):
        self.llm = OllamaLLM(model=model_name)

    # ── Public interface ───────────────────────────────────────────────────────

    def evaluate_response(self, question: str, answer: str, contexts: list) -> dict | None:
        """Evaluates response quality using LLM-as-judge with heuristic fallback.

        Primary path: asks the same local LLM to score faithfulness and relevancy.
        This is significantly more accurate than token-overlap heuristics because
        the model understands synonyms, paraphrases and semantic entailment.

        Fallback: if the LLM judge call fails (Ollama unavailable, malformed JSON),
        the lightweight token-overlap heuristic is used so the system always returns
        a score.
        """
        result = self._llm_judge(question, answer, contexts)
        if result is not None:
            return result
        return self._heuristic(question, answer, contexts)

    # ── Private methods ────────────────────────────────────────────────────────

    def _llm_judge(self, question: str, answer: str, contexts: list) -> dict | None:
        """Calls the LLM to score faithfulness and relevancy of the answer."""
        try:
            context_text = "\n".join(contexts[:3])[:1500]
            prompt = _JUDGE_PROMPT.format(
                question=question[:400],
                answer=answer[:900],
                context=context_text,
            )
            response = self.llm.invoke(prompt)

            # Strip DeepSeek reasoning tags if present
            if "</thought>" in response:
                response = response.split("</thought>", 1)[1]

            match = re.search(r'\{[\s\S]*\}', response.strip())
            if not match:
                return None

            scores = json.loads(match.group())
            f = round(min(max(float(scores.get("faithfulness", 0)), 0.0), 1.0), 2)
            r = round(min(max(float(scores.get("relevancy", 0)), 0.0), 1.0), 2)
            return {"faithfulness": f, "relevancy": r, "method": "llm_judge"}
        except Exception as e:
            print(f"LLM judge evaluation failed, falling back to heuristic: {e}")
            return None

    def _heuristic(self, question: str, answer: str, contexts: list) -> dict | None:
        """Token-overlap heuristic — fast fallback when the LLM judge is unavailable."""
        try:
            combined_context = " ".join(contexts).lower()
            answer_lower = answer.lower()
            question_lower = question.lower()

            answer_tokens = set(answer_lower.split())
            context_tokens = set(combined_context.split())
            faithfulness = len(answer_tokens & context_tokens) / max(len(answer_tokens), 1)

            question_tokens = set(question_lower.split())
            relevancy = len(question_tokens & answer_tokens) / max(len(question_tokens), 1)

            return {
                "faithfulness": round(min(max(faithfulness, 0.0), 1.0), 2),
                "relevancy": round(min(max(relevancy, 0.0), 1.0), 2),
                "method": "heuristic",
            }
        except Exception as e:
            print(f"Heuristic evaluation error: {e}")
            return None

    # ── RAGAS production path (for future activation) ─────────────────────────
    # def _ragas_evaluate(self, question, answer, contexts):
    #     from ragas import evaluate
    #     from ragas.metrics import faithfulness, answer_relevancy
    #     from datasets import Dataset
    #     data = Dataset.from_dict({
    #         "question": [question], "answer": [answer], "contexts": [contexts]
    #     })
    #     result = evaluate(data, metrics=[faithfulness, answer_relevancy], llm=...)
    #     return {"faithfulness": result["faithfulness"],
    #             "relevancy": result["answer_relevancy"], "method": "ragas"}
