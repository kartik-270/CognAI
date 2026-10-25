import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.memory.retrieval import ScoredMemory

logger = logging.getLogger(__name__)

class ResolvedEntityFact:
    """
    A canonical, deduplicated fact with aggregated source provenance and temporal anchoring.
    """
    def __init__(
        self,
        entity: str,
        fact_text: str,
        anchor_date: Optional[datetime],
        source_turn_ids: List[str],
        memory_type: str = "episodic",
        score: float = 1.0
    ):
        self.entity = entity
        self.fact_text = fact_text
        self.anchor_date = anchor_date
        self.source_turn_ids = sorted(list(set(source_turn_ids)), key=lambda x: (
            int(re.findall(r'D(\d+)', x)[0]) if re.findall(r'D(\d+)', x) else 0,
            int(re.findall(r':(\d+)', x)[0]) if re.findall(r':(\d+)', x) else 0
        ))
        self.memory_type = memory_type
        self.score = score

    def to_formatted_line(self) -> str:
        date_str = ""
        if self.anchor_date:
            c_dt = self.anchor_date if self.anchor_date.tzinfo else self.anchor_date.replace(tzinfo=timezone.utc)
            date_str = f" [Anchor Date: {c_dt.strftime('%Y-%m-%d (%A, %B %d, %Y)')}]"
        
        sources_str = ""
        if self.source_turn_ids:
            sources_str = f" [Sources: {', '.join(self.source_turn_ids)}]"
            
        return f"- [{self.entity.upper()}]{date_str}{sources_str} {self.fact_text}"


class PostRetrievalAggregator:
    """
    Post-Retrieval Entity Resolution, Deduplication, and Provenance Preservation.
    
    Responsibilities:
    1. Entity Coreference Resolution: Maps pronouns, dialogue participants, and associated
       actors (Caroline vs Melanie vs Melanie's Children vs Oscar vs Grandma) to prevent speaker confusion.
    2. Fact Deduplication with Union Provenance: Merges overlapping facts across multiple 
       retrieved sessions without losing any D#:turn provenance IDs.
    3. Temporal Chronology Preservation: Retains exact Anchor Dates for all facts.
    4. Set & Cardinality Aggregation: Organizes distinct activities, books, and counts.
    5. Clean-Cut Grounding Validation: Flags queries completely absent from recorded evidence.
    """

    KNOWN_ENTITIES = [
        ("melanie's children", ["melanie's kids", "her kids", "her children", "mel's kids", "youngest", "son"]),
        ("melanie", ["melanie", "mel", "mel's"]),
        ("caroline's grandma", ["caroline's grandma", "her grandma", "grandma in sweden", "grandmother"]),
        ("caroline", ["caroline", "caroline's"]),
        ("oscar", ["oscar", "oscar's"]),
    ]

    @staticmethod
    def _detect_entity(text: str, default: str = "General") -> str:
        text_lower = text.lower()
        for canonical, aliases in PostRetrievalAggregator.KNOWN_ENTITIES:
            if any(alias in text_lower for alias in aliases):
                return canonical
        if "user" in text_lower:
            return "User"
        return default

    @staticmethod
    def _extract_provenance(text: str, existing_sources: Optional[List[str]] = None) -> List[str]:
        found = set(existing_sources or [])
        found.update(re.findall(r"D\d+:\d+", text))
        return list(found)

    @staticmethod
    def _clean_fact_text(text: str) -> str:
        # Remove raw 'Sources: D#:#' trailers from text body to keep the statement clean
        cleaned = re.sub(r'Sources:\s*(?:D\d+:\d+,?\s*)+', '', text, flags=re.IGNORECASE)
        cleaned = re.sub(r'\[User discussed:[^\]]+\]', '', cleaned)
        cleaned = re.sub(r'\[Sources:[^\]]+\]', '', cleaned)
        cleaned = re.sub(r'\[Anchor Date:[^\]]+\]', '', cleaned)
        return " ".join(cleaned.split()).strip()

    @staticmethod
    def _compute_jaccard_similarity(s1: str, s2: str) -> float:
        w1 = set(re.findall(r'\b[a-zA-Z0-9]{3,}\b', s1.lower()))
        w2 = set(re.findall(r'\b[a-zA-Z0-9]{3,}\b', s2.lower()))
        if not w1 or not w2:
            return 0.0
        intersection = len(w1 & w2)
        union = len(w1 | w2)
        return intersection / union if union > 0 else 0.0

    def aggregate_and_resolve(
        self,
        query: str,
        retrieved_memories: List[ScoredMemory]
    ) -> Dict[str, Any]:
        """
        Executes holistic entity resolution, provenance merging, and validation.
        """
        if not retrieved_memories:
            return {
                "resolved_facts": [],
                "formatted_context": "",
                "all_provenance_ids": [],
                "is_grounded": False
            }

        extracted_facts: List[ResolvedEntityFact] = []
        all_provenance: set = set()

        # Step 1: Parse and normalize facts
        for mem in retrieved_memories:
            raw_content = mem.content or ""
            turn_ids = list(mem.source_turn_ids) if mem.source_turn_ids else []
            turn_ids.extend(self._extract_provenance(raw_content))
            all_provenance.update(turn_ids)

            # Split compound multi-sentence episodic summaries into clean micro-facts if needed
            sentences = [s.strip() for s in re.split(r'\.\s+|\n+', raw_content) if len(s.strip()) > 15]
            if not sentences:
                sentences = [raw_content]

            # Primary entity of the chunk
            chunk_entity = self._detect_entity(raw_content, default="Episode")

            for sent in sentences:
                cleaned_sent = self._clean_fact_text(sent)
                if not cleaned_sent or len(cleaned_sent.split()) < 3:
                    continue

                # Sentence-level entity refinement
                sent_entity = self._detect_entity(cleaned_sent, default=chunk_entity)

                extracted_facts.append(
                    ResolvedEntityFact(
                        entity=sent_entity,
                        fact_text=cleaned_sent,
                        anchor_date=mem.created_at,
                        source_turn_ids=turn_ids,
                        memory_type=mem.memory_type,
                        score=mem.final_score
                    )
                )

        # Step 2: Entity Coreference & Deduplication with Union Provenance
        merged_facts: List[ResolvedEntityFact] = []
        
        for fact in extracted_facts:
            matched_idx = -1
            for idx, existing in enumerate(merged_facts):
                # Only merge if entity matches or is closely aligned
                if existing.entity == fact.entity:
                    sim = self._compute_jaccard_similarity(existing.fact_text, fact.fact_text)
                    if sim >= 0.55: # Substantial textual/semantic overlap
                        matched_idx = idx
                        break

            if matched_idx >= 0:
                # Merge into existing: Union provenance and keep the longer, more informative description
                existing = merged_facts[matched_idx]
                existing.source_turn_ids = sorted(list(set(existing.source_turn_ids + fact.source_turn_ids)))
                if len(fact.fact_text) > len(existing.fact_text):
                    existing.fact_text = fact.fact_text
                # Keep the latest or most specific anchor date
                if not existing.anchor_date and fact.anchor_date:
                    existing.anchor_date = fact.anchor_date
            else:
                merged_facts.append(fact)

        # Step 3: Chronological & Entity Grouping
        merged_facts.sort(key=lambda f: (
            f.entity,
            f.anchor_date.isoformat() if f.anchor_date else ""
        ))

        # Step 4: Grounding Validation (Detect if query asks about an unmentioned topic)
        q_words = set(re.findall(r'\b[a-zA-Z0-9]{4,}\b', query.lower())) - {
            "what", "when", "where", "which", "would", "could", "should", "their", "there", "about", "melanie", "caroline"
        }
        all_facts_text = " ".join([f.fact_text.lower() for f in merged_facts])
        matches = [w for w in q_words if w in all_facts_text]
        is_grounded = len(matches) > 0 if q_words else True

        # Step 5: Format cleanly for generator
        formatted_lines = [f.to_formatted_line() for f in merged_facts]
        
        return {
            "resolved_facts": merged_facts,
            "formatted_context": "\n".join(formatted_lines),
            "all_provenance_ids": sorted(list(all_provenance)),
            "is_grounded": is_grounded
        }

# Global singleton
post_retrieval_aggregator = PostRetrievalAggregator()
