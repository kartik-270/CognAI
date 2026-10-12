import asyncio
import os
import sys
import json
import logging
from typing import List, Dict, Any
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("CognAIBenchmark")

try:
    from datasets import load_dataset
except ImportError:
    logger.error("The 'datasets' library is required. Run: pip install datasets")
    sys.exit(1)

# Import CognAI backend components (Requires DB & Neo4j to be running)
try:
    from app.db.session import async_session
    from app.brain.orchestrator import CognitiveOrchestrator
except ImportError:
    logger.warning("Could not import CognAI modules. Ensure you are running this from the backend root.")

class BenchmarkHarness:
    """
    Evaluates CognAI against long-term memory benchmarks like LoCoMo.
    """
    def __init__(self, limit: int = 50):
        self.limit = limit
        self.results = []
        
    async def evaluate_locomo(self):
        logger.info(f"Loading LoCoMo dataset (evaluating first {self.limit} samples)...")
        # Note: 'qiaojin/LoCoMo' is a placeholder for the actual HF dataset path if available
        # Using a simulated structure of LoCoMo for the harness
        dataset = load_dataset("qiaojin/LoCoMo", split="test", streaming=True)
        
        async with async_session() as db:
            orchestrator = CognitiveOrchestrator(db)
            
            count = 0
            correct = 0
            
            for item in dataset:
                if count >= self.limit:
                    break
                    
                user_id = f"benchmark_user_{count}"
                history = item['history'] # List of previous turns
                question = item['question']
                ground_truth = item['answer']
                
                logger.info(f"--- Evaluating Sample {count+1} ---")
                
                # 1. Feed history into CognAI to build the memory state
                for turn in history:
                    # We bypass the full LLM generation for history to save time,
                    # just processing the incoming turn for working memory / consolidation
                    await orchestrator.step(user_id=user_id, prompt=turn['user'])
                
                # 2. Ask the benchmark question
                result = await orchestrator.step(user_id=user_id, prompt=question)
                generated_answer = result['response']
                
                # 3. Evaluate using LLM-as-a-judge (gemma-31b-it)
                logger.info("Calling LLM Judge (gemma-31b-it) for evaluation...")
                try:
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    import os
                    
                    judge_llm = ChatGoogleGenerativeAI(
                        model="gemma-31b-it",
                        api_key=os.getenv("GEMINI_API_KEY", "dummy_key"),
                        temperature=0.0
                    )
                    
                    prompt = (
                        f"You are an expert evaluator. Given the question, the expected ground truth, "
                        f"and the AI's generated answer, determine if the AI's answer is conceptually correct.\n\n"
                        f"Question: {question}\n"
                        f"Ground Truth: {ground_truth}\n"
                        f"Generated Answer: {generated_answer}\n\n"
                        f"Output ONLY 'TRUE' if the generated answer is correct, or 'FALSE' if it is incorrect."
                    )
                    
                    judge_response = await judge_llm.ainvoke(prompt)
                    is_correct = "TRUE" in judge_response.content.upper()
                except Exception as e:
                    logger.warning(f"LLM Judge failed ({e}), falling back to substring match.")
                    is_correct = ground_truth.lower() in generated_answer.lower()

                if is_correct:
                    correct += 1
                    
                self.results.append({
                    "user_id": user_id,
                    "question": question,
                    "expected": ground_truth,
                    "generated": generated_answer,
                    "correct": is_correct,
                    "cognitive_trace": result.get('cognitive_trace')
                })
                count += 1
                
            accuracy = (correct / count) * 100 if count > 0 else 0
            logger.info(f"LoCoMo Benchmark Complete. Accuracy: {accuracy:.2f}% ({correct}/{count})")
            
            # Save results
            with open("locomo_benchmark_results.json", "w") as f:
                json.dump({"accuracy": accuracy, "details": self.results}, f, indent=2)

if __name__ == "__main__":
    print("="*60)
    print("COGNAI LIVE BENCHMARK HARNESS (LongMemEval / LoCoMo)")
    print("="*60)
    print("WARNING: This script requires a running PostgreSQL (pgvector) and Neo4j instance.")
    print("It will make live LLM API calls via your configured providers (Groq/Gemini).")
    
    confirm = input("Are your databases running and API keys set in .env? (y/n): ")
    if confirm.lower() == 'y':
        harness = BenchmarkHarness(limit=50) # Set to 50 for a quick test, scale to 1000+ for full paper
        asyncio.run(harness.evaluate_locomo())
    else:
        print("Benchmark aborted. Please start your databases and configure .env first.")
