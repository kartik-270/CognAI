import os
import re
import logging
import asyncio
import random
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def _normalize_answer(s: Any) -> str:
    """Lower text and trim punctuation, articles and extra whitespace."""
    s = str(s if s is not None else "").lower()
    s = re.sub(r'\b(a|an|the)\b', ' ', s)
    s = re.sub(r'[^\w\s]', ' ', s)
    return " ".join(s.split())

def compute_token_f1(prediction: str, ground_truth: str) -> Dict[str, float]:
    """
    Standard SQuAD/LoCoMo token-level F1, Precision, Recall, and Exact Match metrics.
    Publication-standard NLP evaluation baseline.
    """
    pred_tokens = _normalize_answer(prediction).split()
    truth_tokens = _normalize_answer(ground_truth).split()

    if not pred_tokens and not truth_tokens:
        return {"f1": 100.0, "precision": 100.0, "recall": 100.0, "exact_match": 100.0}
    if not pred_tokens or not truth_tokens:
        return {"f1": 0.0, "precision": 0.0, "recall": 0.0, "exact_match": 0.0}

    common = set(pred_tokens) & set(truth_tokens)
    num_same = sum(min(pred_tokens.count(w), truth_tokens.count(w)) for w in common)

    if num_same == 0:
        return {"f1": 0.0, "precision": 0.0, "recall": 0.0, "exact_match": 0.0}

    precision = 1.0 * num_same / len(pred_tokens)
    recall = 1.0 * num_same / len(truth_tokens)
    f1 = (2 * precision * recall) / (precision + recall)
    exact_match = 1.0 if _normalize_answer(prediction) == _normalize_answer(ground_truth) else 0.0

    return {
        "f1": round(f1 * 100, 2),
        "precision": round(precision * 100, 2),
        "recall": round(recall * 100, 2),
        "exact_match": round(exact_match * 100, 2)
    }

class ResearchEvaluator:
    """
    Publication-grade multi-dimensional benchmark evaluator.
    Combines:
    1. Deterministic Token-Level Metrics (F1, Precision, Recall, Exact Match)
    2. LLM-as-a-judge Multi-Dimensional Metrics (Correctness, Completeness, Faithfulness: 0-2)
    3. Retrieval Diagnostics (Recall@K, Hit@K)
    4. Jittered Exponential Backoff for resilience against API 500 / 429 server errors.
    """
    def __init__(self, model_name: str = "gemma-4-31b-it", max_retries: int = 4):
        self.model_name = model_name
        self.max_retries = max_retries
        self.llm_available = False
        self.judge_llm = None
        self._init_judge()

    def _init_judge(self):
        try:
            aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
            if aws_access_key:
                from langchain_aws import ChatBedrock
                secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
                self.judge_llm = ChatBedrock(
                    model_id=os.getenv("AWS_BEDROCK_MODEL", "qwen.qwen3-32b-v1:0"),
                    region_name=os.getenv("AWS_REGION", "ap-southeast-2"),
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=secret_key,
                    model_kwargs={"temperature": 0.0}
                )
                self.llm_available = True
                self.model_name = "aws-bedrock-gateway"
                logger.info(f"ResearchEvaluator initialized with AWS Bedrock model: {self.model_name}")
                return

            cloudflare_key = os.getenv("CLOUDFLARE_API_TOKEN")
            if cloudflare_key:
                try:
                    from langchain_openai import ChatOpenAI
                    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
                    self.judge_llm = ChatOpenAI(
                        api_key=cloudflare_key,
                        base_url=f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
                        model=os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.1-8b-instruct-fp8"),
                        temperature=0.0
                    )
                    self.llm_available = True
                    self.model_name = "cloudflare-gateway"
                    logger.info(f"ResearchEvaluator initialized with Cloudflare model: {self.model_name}")
                    return
                except ImportError:
                    logger.warning("langchain_openai not installed.")

            ollama_model = os.getenv("OLLAMA_JUDGE_MODEL")
            if ollama_model:
                from langchain_community.chat_models import ChatOllama
                self.judge_llm = ChatOllama(model=ollama_model, temperature=0.0)
                self.llm_available = True
                self.model_name = ollama_model
                logger.info(f"ResearchEvaluator initialized with Local Runtime judge model: {self.model_name}")
                return

            from langchain_google_genai import ChatGoogleGenerativeAI
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                logger.warning("GEMINI_API_KEY not set. Evaluator running in deterministic NLP mode.")
                return
                
            self.judge_llm = ChatGoogleGenerativeAI(
                model=self.model_name,
                api_key=api_key,
                temperature=0.0,
                max_retries=5,
                request_timeout=30.0
            )
            self.llm_available = True
            logger.info(f"ResearchEvaluator initialized with judge model: {self.model_name}")
        except Exception as e:
            logger.warning(f"Could not initialize judge: {e}")
            self.llm_available = False

    async def _invoke_judge_with_retry(self, prompt: str) -> str:
        """Executes judge call with randomized exponential backoff and fallback models to handle 500 errors."""
        from dotenv import load_dotenv
        load_dotenv(override=True)
        
        aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        if aws_access_key:
            from langchain_aws import ChatBedrock
            try:
                secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
                client = ChatBedrock(
                    model_id=os.getenv("AWS_BEDROCK_MODEL", "qwen.qwen3-32b-v1:0"),
                    region_name=os.getenv("AWS_REGION", "ap-southeast-2"),
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=secret_key,
                    model_kwargs={"temperature": 0.0}
                )
                response = await client.ainvoke(prompt)
                return str(response.content)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to use AWS Bedrock: {e}")

        cloudflare_key = os.getenv("CLOUDFLARE_API_TOKEN")
        if cloudflare_key:
            try:
                from langchain_openai import ChatOpenAI
                account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
                client = ChatOpenAI(
                    api_key=cloudflare_key,
                    base_url=f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
                    model=os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.1-8b-instruct-fp8"),
                    temperature=0.0
                )
                response = await client.ainvoke(prompt)
                return str(response.content)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to use Cloudflare: {e}")

        ollama_model = os.getenv("OLLAMA_JUDGE_MODEL")
        if ollama_model:
            from langchain_community.chat_models import ChatOllama
            client = ChatOllama(model=ollama_model, temperature=0.0)
            response = await client.ainvoke(prompt)
            return str(response.content)

        from langchain_google_genai import ChatGoogleGenerativeAI
        models_to_try = [self.model_name, "gemma-4-31b-it"]
        # Deduplicate while preserving order
        models_to_try = list(dict.fromkeys(models_to_try))
        
        last_error = None
        for model in models_to_try:
            for attempt in range(2):
                try:
                    client = ChatGoogleGenerativeAI(
                        model=model,
                        api_key=os.getenv("GEMINI_API_KEY"),
                        temperature=0.0,
                        max_retries=3,
                        request_timeout=30.0
                    )
                    response = await client.ainvoke(prompt)
                    content = response.content
                    if isinstance(content, list):
                        content = " ".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
                    return str(content)
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    if "429" in err_str or "rate limit" in err_str:
                        wait_time = (4.0 ** attempt) + random.uniform(2.0, 5.0)
                    else:
                        wait_time = (2.0 ** attempt) + random.uniform(1.0, 3.0)
                    logger.warning(f"Judge API {model} attempt {attempt+1} failed: {e}. Retrying in {wait_time:.1f}s...")
                    await asyncio.sleep(wait_time)
        raise RuntimeError(f"Judge LLM failed after trying models {models_to_try}: {last_error}")

    async def evaluate_answer(
        self, 
        question: str, 
        ground_truth: str, 
        generated_answer: str, 
        evidence: str = "N/A"
    ) -> Dict[str, Any]:
        """
        Evaluates generated answer against ground truth across both deterministic F1 and LLM-as-a-judge dimensions.
        """
        # 1. Deterministic NLP baseline (always available and fast)
        nlp_metrics = compute_token_f1(generated_answer, ground_truth)

        # 2. LLM-as-a-Judge Evaluation
        judge_scores = {
            "correctness": 0,
            "completeness": 0,
            "faithfulness": 0,
            "judge_failed": True,
            "raw_output": ""
        }

        if not self.llm_available or not self.judge_llm:
            return {**nlp_metrics, **judge_scores}

        prompt = (
            "You are an expert academic evaluator for a Long-Term Memory AI benchmark.\n"
            "Evaluate the Generated Answer against the Question, Ground Truth, and Supporting Evidence on three dimensions (0 to 2):\n"
            "- Correctness (0=incorrect, 1=partially correct, 2=fully correct. *IMPORTANT*: If the question is a hallucination/adversarial and the answer politely refuses to answer or states it has no information, score CORRECTNESS as 2)\n"
            "- Completeness (0=missing key details, 1=partially complete, 2=fully complete)\n"
            "- Faithfulness (0=hallucinated claims not in evidence, 1=minor ungrounded claim, 2=strictly faithful)\n\n"
            f"Question: {question}\n"
            f"Ground Truth: {ground_truth}\n"
            f"Supporting Evidence: {evidence}\n"
            f"Generated Answer: {generated_answer}\n\n"
            "Format your response EXACTLY as:\n"
            "CORRECTNESS: [0, 1, or 2]\n"
            "COMPLETENESS: [0, 1, or 2]\n"
            "FAITHFULNESS: [0, 1, or 2]"
        )

        try:
            content = await self._invoke_judge_with_retry(prompt)
            content_upper = content.upper()

            def extract_score(metric: str) -> int:
                # Find the metric name, skip any characters until we see a 0, 1, or 2
                # But ensure we don't accidentally match a year or something.
                # Looking for: metric name, optionally "score", some separator, then the number.
                patterns = [
                    rf"[\"\'\*\*]*{metric}[\"\'\*\*]*\s*(?:SCORE)?\s*[:=\-]\s*\[?([0-2])\]?",
                    rf"{metric}.*?(?:[:=]|-)\s*([0-2])\b",
                    rf"{metric}[^0-2\n]*([0-2])"
                ]
                for p in patterns:
                    m = re.search(p, content_upper)
                    if m:
                        return int(m.group(1))
                raise ValueError(f"Could not parse score for {metric}. Raw output: {content}")

            judge_scores = {
                "correctness": extract_score("CORRECTNESS"),
                "completeness": extract_score("COMPLETENESS"),
                "faithfulness": extract_score("FAITHFULNESS"),
                "judge_failed": False,
                "raw_output": content,
                "judge_model": self.model_name
            }
        except Exception as e:
            logger.warning(f"Judge LLM evaluation failed after retries: {e}")
            judge_scores = {
                "correctness": None,
                "completeness": None,
                "faithfulness": None,
                "judge_failed": True,
                "raw_output": "",
                "judge_model": self.model_name
            }

        return {**nlp_metrics, **judge_scores}

    def evaluate_retrieval(
        self, 
        retrieved_memories: List[Dict[str, Any]], 
        expected_evidence_ids: List[str]
    ) -> Dict[str, float]:
        """
        Calculates Retrieval Recall@K and Hit@K against the ground-truth evidence turn IDs.
        """
        ev = {m for e in expected_evidence_ids for m in re.findall(r"D\d+:\d+", str(e))}
        if not ev: 
            return {"recall_at_k": None, "hit_at_k": None, "k": len(retrieved_memories)}

        got = {s for m in retrieved_memories for s in m.get("source_turn_ids", [])}
        if not got:
            retrieved_text = " ".join([m.get("content", "") for m in retrieved_memories])
            got = set(re.findall(r"D\d+:\d+", retrieved_text))
            
        r = len(ev & got) / len(ev)
        return {
            "recall_at_k": round(r * 100, 2),
            "hit_at_k": round(float(r > 0) * 100, 2),
            "k": len(retrieved_memories)
        }
