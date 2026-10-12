from sqlalchemy import Column, String, Float, DateTime, func, Boolean, Integer, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy.types import TypeDecorator
    from sqlalchemy import JSON
    class Vector(TypeDecorator):
        impl = JSON
        cache_ok = True
        def __init__(self, dim=1024, *args, **kwargs):
            self.dim = dim
            super().__init__(*args, **kwargs)

from sqlalchemy.orm import declarative_base
import uuid

Base = declarative_base()


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    
    # Core memory vectors (bge-m3 produces 1024-dim dense vectors)
    # The requirement is strict adherence to vector(1024)
    embedding = Column(Vector(1024))
    
    raw_summary = Column(Text)
    
    # Emotional Memory tags (-1.0 to 1.0 valence, 0.0 to 1.0 intensity)
    emotional_valence = Column(Float, default=0.0)
    emotional_intensity = Column(Float, default=0.0)
    
    # Cognitive surprise score (cosine distance to historical centroid)
    surprise_score = Column(Float, default=0.0)
    
    turn_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PermanentMemory(Base):
    __tablename__ = "permanent_memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    fact = Column(Text, nullable=False)
    category = Column(String, default="fact")  # preference, identity, belief, knowledge
    confidence = Column(Float, default=1.0)
    
    # 1024-dim vector for semantic search
    embedding = Column(Vector(1024))
    
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Goal(Base):
    __tablename__ = "goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="active")  # active, completed, stalled, abandoned
    
    # 1024-dim vector for goal-conditioned retrieval & forgetting
    embedding = Column(Vector(1024), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PersonaProfile(Base):
    __tablename__ = "persona_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, unique=True, nullable=False, index=True)
    
    # 5-Signal Persona Drift Metrics
    verbosity_ratio = Column(Float, default=1.0)       # user words / assistant words
    rephrasing_rate = Column(Float, default=0.0)       # ratio of detected rephrasings
    formality_score = Column(Float, default=0.5)       # 0.0 (casual) to 1.0 (formal)
    question_frequency = Column(Float, default=0.2)    # ratio of questions asked by user
    topic_return_rate = Column(Float, default=0.1)     # rate of returning to unresolved topics
    
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)  # Null if Google OAuth
    is_active = Column(Boolean, default=True)
    session_count = Column(Integer, default=0)       # Track sessions for cold start logic
    
    # Two-phase /forget-me compliance fields
    deletion_pending = Column(Boolean, default=False)
    deletion_requested_at = Column(DateTime(timezone=True), nullable=True)
    
    is_verified = Column(Boolean, default=False) # True if Google OAuth or OTP verified
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RegistrationState(Base):
    __tablename__ = "registration_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    step = Column(Integer, default=1)  # 1: email collected, 2: password collected
    hashed_password = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OTPCode(Base):
    __tablename__ = "otp_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, index=True, nullable=False)
    code = Column(String, nullable=False)
    purpose = Column(String, nullable=False)  # 'register', 'forget_password'
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    """Stores raw chat messages purely for UI history display (like ChatGPT)."""
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    cognitive_trace = Column(JSON, nullable=True)  # To store trace for the UI
    attachments = Column(JSON, nullable=True)  # Attached documents and images metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentAttachment(Base):
    __tablename__ = "document_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    storage_path = Column(String, nullable=False)
    extracted_text = Column(Text, nullable=True)
    is_image = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
