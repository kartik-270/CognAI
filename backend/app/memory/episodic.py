from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Dict, Any, Optional
import numpy as np
import json
import re
from datetime import datetime

from app.db.models import Episode
from app.llm.router import llm_router

EMOTIONAL_RUBRIC_PROMPT = """
You are a cognitive psychology analyzer. Analyze the following conversation session and produce a structured emotional analysis and concise summary.

Scoring Rubric:
- emotional_valence: Float between -1.0 and +1.0
  - -1.0 to -0.6: Deeply frustrated, angry, distressed, or highly anxious
  - -0.5 to -0.1: Mildly annoyed, disappointed, confused, or expressing difficulty
  -  0.0: Strictly robotic, detached, or purely factual transactional
  - +0.1 to +0.4: Constructive, focused, inquisitive, engaged, or collaborative
  - +0.5 to +0.7: Pleased, relieved, appreciative, or satisfied
  - +0.8 to +1.0: Highly enthusiastic, euphoric, or thrilled
- emotional_intensity: Float between 0.0 and 1.0
  - 0.0 to 0.2: Detached, casual banter
  - 0.3 to 0.6: Moderate engagement, focused project work or inquiry
  - 0.7 to 1.0: High passion, urgency, deep personal investment, or severe stress

Session Transcript:
\"\"\"
{transcript}
\"\"\"

Return ONLY a valid JSON object with keys:
{{
  "summary": "1-3 sentence summary of the core discussion and any resolutions",
  "emotional_valence": <float between -1.0 and 1.0>,
  "emotional_intensity": <float between 0.0 and 1.0>
}}
"""

class EpisodicMemoryManager:
    """
    Manages episodic memory writes, cosine-distance surprise calculations,
    and structured emotional valence tagging.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_surprise_score(self, user_id: str, new_embedding: List[float]) -> float:
        """
        Calculates cosine distance surprise relative to user's historical episode centroid.
        Surprise = 1.0 - CosineSimilarity(new_embedding, centroid)
        """
        # Fetch last 20 episodes for this user to compute running centroid
        stmt = select(Episode.embedding).where(
            Episode.user_id == user_id,
            Episode.embedding.isnot(None)
        ).order_by(Episode.created_at.desc()).limit(20)
        
        result = await self.db.execute(stmt)
        embeddings = [row[0] for row in result.all() if row[0] is not None]

        if not embeddings:
            return 0.5  # Baseline surprise on cold start

        emb_matrix = np.array(embeddings)
        centroid = np.mean(emb_matrix, axis=0)
        
        norm_new = np.linalg.norm(new_embedding)
        norm_cent = np.linalg.norm(centroid)
        
        if norm_new == 0 or norm_cent == 0:
            return 0.5
            
        cosine_sim = np.dot(new_embedding, centroid) / (norm_new * norm_cent)
        surprise = float(np.clip(1.0 - cosine_sim, 0.0, 1.0))
        return surprise

    async def extract_session_emotions_and_summary(self, transcript: str) -> Dict[str, Any]:
        """
        Uses background LLM (Gemini 2.0 Flash) to tag emotional valence and summarize.
        """
        prompt = EMOTIONAL_RUBRIC_PROMPT.format(transcript=transcript)
        raw_output = await llm_router.background_task(prompt)
        
        try:
            clean_output = raw_output.replace("```json", "").replace("```", "").strip()
            json_match = re.search(r'\{.*\}', clean_output, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                valence = float(np.clip(float(parsed.get("emotional_valence", 0.0)), -1.0, 1.0))
                intensity = float(np.clip(float(parsed.get("emotional_intensity", 0.0)), 0.0, 1.0))
                summary = parsed.get("summary", transcript[:200])
                return {
                    "summary": summary,
                    "emotional_valence": round(valence, 2),
                    "emotional_intensity": round(intensity, 2)
                }
        except Exception:
            pass

        return {
            "summary": transcript[:250],
            "emotional_valence": 0.0,
            "emotional_intensity": 0.0
        }

    async def record_episode(
        self,
        user_id: str,
        session_id: str,
        transcript: str,
        turn_count: int,
        session_timestamp: Optional[datetime] = None
    ) -> Episode:
        """
        Creates, tags, embeds, and commits episodic memory row(s).
        For long sessions (>20 turns), chunks into 20-turn episode windows grouped under the same session_id
        so no turn-level context, speaker dialogue, or source IDs are lost.
        """
        raw_lines = [line.strip() for line in transcript.split("\n") if line.strip()]
        
        # If transcript exceeds 20 turns, chunk into ~20-turn segments with 2-turn overlap
        CHUNK_SIZE = 20
        OVERLAP = 2
        
        if len(raw_lines) > CHUNK_SIZE:
            chunks = []
            i = 0
            while i < len(raw_lines):
                chunk_slice = raw_lines[i : i + CHUNK_SIZE]
                chunks.append(chunk_slice)
                if i + CHUNK_SIZE >= len(raw_lines):
                    break
                i += CHUNK_SIZE - OVERLAP
        else:
            chunks = [raw_lines]

        # 1. Emotional tagging & global summary via secondary LLM for the session
        analysis = await self.extract_session_emotions_and_summary(transcript)
        session_summary = analysis["summary"]

        created_episodes = []
        for idx, chunk in enumerate(chunks):
            chunk_text = "\n".join(chunk)
            chunk_source_ids = re.findall(r"D\d+:\d+", chunk_text)
            
            # Build robust summary for this chunk
            part_suffix = f" (Part {idx+1}/{len(chunks)})" if len(chunks) > 1 else ""
            chunk_content = f"{session_summary}{part_suffix}\nFull Dialogue Segment:\n{chunk_text}"
            if chunk_source_ids:
                chunk_content += "\nSources: " + ", ".join(list(dict.fromkeys(chunk_source_ids)))

            # Compute embedding for chunk
            embedding = await llm_router.embed(chunk_content)
            surprise = await self.compute_surprise_score(user_id, embedding)

            ep = Episode(
                user_id=user_id,
                session_id=session_id,
                raw_summary=chunk_content,
                embedding=embedding,
                emotional_valence=analysis["emotional_valence"],
                emotional_intensity=analysis["emotional_intensity"],
                surprise_score=surprise,
                turn_count=len(chunk)
            )
            if session_timestamp is not None:
                ep.created_at = session_timestamp

            self.db.add(ep)
            created_episodes.append(ep)

        await self.db.commit()
        for ep in created_episodes:
            await self.db.refresh(ep)
            
        return created_episodes[0]

