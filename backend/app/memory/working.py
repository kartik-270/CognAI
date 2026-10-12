from pydantic import BaseModel, Field
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime, timezone
import uuid
import re

class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_id: Optional[str] = None

class RephrasingDetector:
    """
    Detects if the user is repeating or rephrasing an unresolved query.
    Used for 5-signal persona drift and metacognitive uncertainty estimation.
    """
    @staticmethod
    def _tokenize(text: str) -> set:
        words = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
        # Filter basic stopwords
        stopwords = {"is", "a", "the", "and", "or", "to", "in", "of", "it", "i", "you", "my", "me", "do", "can"}
        return {w for w in words if w not in stopwords}

    def check_rephrasing(self, current_prompt: str, recent_messages: List[Message], threshold: float = 0.5) -> Tuple[bool, float]:
        """
        Calculates Jaccard overlap against the most recent user messages.
        Returns (is_rephrase, overlap_score).
        """
        curr_tokens = self._tokenize(current_prompt)
        if not curr_tokens or len(curr_tokens) < 2:
            return False, 0.0

        user_messages = [m for m in recent_messages if m.role == "user"]
        if not user_messages:
            return False, 0.0

        # Compare primarily against the last 2 user messages
        max_score = 0.0
        for prev_msg in user_messages[-2:]:
            prev_tokens = self._tokenize(prev_msg.content)
            if not prev_tokens:
                continue
            intersection = curr_tokens.intersection(prev_tokens)
            union = curr_tokens.union(prev_tokens)
            score = len(intersection) / len(union) if union else 0.0
            if score > max_score:
                max_score = score

        is_rephrase = max_score >= threshold
        return is_rephrase, max_score


class WorkingMemory:
    """
    Manages the short-term working memory of the conversation.
    - Caps context at 20 turns (sliding window) as per Priority Stack.
    - Implements lazy session boundary logic (delta > 30 min triggers consolidation).
    - Incorporates rephrasing detection.
    """
    def __init__(self, user_id: str, capacity: int = 20, session_timeout_minutes: int = 30):
        self.user_id = user_id
        self.capacity = capacity
        self.session_timeout_seconds = session_timeout_minutes * 60
        self.current_session_id: str = str(uuid.uuid4())
        self.messages: List[Message] = []
        self.last_interaction: datetime = datetime.now(timezone.utc)
        self.rephrase_detector = RephrasingDetector()

    def process_incoming_turn(self, role: str, content: str, timestamp: Optional[datetime] = None, source_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Lazily checks for session boundary BEFORE adding the message.
        If delta > 30 min, signals that the previous session ended and must be consolidated.
        """
        now = timestamp if timestamp else datetime.now(timezone.utc)
        if not now.tzinfo:
            now = now.replace(tzinfo=timezone.utc)
            
        time_delta = (now - self.last_interaction).total_seconds()
        
        session_expired = False
        expired_session_id = None
        expired_messages: List[Message] = []
        expired_session_timestamp = None

        # Lazy boundary check: only fires when NEXT message arrives
        if len(self.messages) > 0 and time_delta > self.session_timeout_seconds:
            session_expired = True
            expired_session_id = self.current_session_id
            expired_messages = list(self.messages)
            expired_session_timestamp = expired_messages[0].timestamp
            
            # Start fresh session for incoming message
            self.current_session_id = str(uuid.uuid4())
            self.messages = []

        # Check rephrasing if this is a user message
        is_rephrasing = False
        rephrase_score = 0.0
        if role == "user":
            is_rephrasing, rephrase_score = self.rephrase_detector.check_rephrasing(content, self.messages)

        # Append new message
        msg = Message(role=role, content=content, timestamp=now, source_id=source_id)
        self.messages.append(msg)
        
        # Enforce 20-turn sliding window cap
        if len(self.messages) > self.capacity:
            self.messages = self.messages[-self.capacity:]

        self.last_interaction = now

        return {
            "session_id": self.current_session_id,
            "session_expired": session_expired,
            "expired_session_id": expired_session_id,
            "expired_messages": expired_messages,
            "expired_session_timestamp": expired_session_timestamp,
            "is_rephrasing": is_rephrasing,
            "rephrase_score": rephrase_score,
            "message": msg
        }

    def add_assistant_response(self, content: str) -> Message:
        now = datetime.now(timezone.utc)
        msg = Message(role="assistant", content=content, timestamp=now)
        self.messages.append(msg)
        if len(self.messages) > self.capacity:
            self.messages = self.messages[-self.capacity:]
        self.last_interaction = now
        return msg

    def flush_on_shutdown(self) -> Optional[Dict[str, Any]]:
        """
        Graceful app shutdown flush: consolidates active session if messages exist.
        """
        if self.messages:
            return {
                "session_id": self.current_session_id,
                "messages": list(self.messages),
                "timestamp": datetime.now(timezone.utc)
            }
        return None

    def get_context(self) -> str:
        """Returns the formatted conversation history within the 20-turn cap."""
        lines = []
        for m in self.messages:
            if m.source_id:
                lines.append(f"{m.role.capitalize()} [{m.source_id}]: {m.content}")
            else:
                lines.append(f"{m.role.capitalize()}: {m.content}")
        return "\n".join(lines)

    def get_turn_count(self) -> int:
        return len(self.messages)
