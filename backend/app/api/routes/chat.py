from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, status, UploadFile, File, Form, Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from app.db.database import get_db, AsyncSessionLocal
from app.db.models import User, ChatMessage, Episode, DocumentAttachment
from sqlalchemy import select, func, desc, case
from app.api.auth import get_current_user, get_user_from_token
from app.brain.orchestrator import CognitiveOrchestrator
from app.services.storage import get_storage_service
from app.services.document_parser import DocumentParserService
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])

class ChatRequest(BaseModel):
    prompt: str
    attachment_ids: Optional[List[str]] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    cognitive_trace: Dict[str, Any]

async def _get_attachments_meta(db: AsyncSession, user_id: str, attachment_ids: Optional[List[str]]) -> Optional[List[Dict[str, Any]]]:
    if not attachment_ids:
        return None
    uuids = []
    for aid in attachment_ids:
        try:
            uuids.append(uuid.UUID(str(aid)))
        except Exception:
            pass
    if not uuids:
        return None
    stmt = select(DocumentAttachment).where(
        DocumentAttachment.id.in_(uuids),
        DocumentAttachment.user_id == user_id
    )
    res = await db.execute(stmt)
    records = res.scalars().all()
    if not records:
        return None
    return [
        {
            "id": str(r.id),
            "file_name": r.file_name,
            "file_type": r.file_type,
            "file_size": r.file_size,
            "is_image": r.is_image
        }
        for r in records
    ]

@router.post("/chat/upload-attachment")
async def upload_attachment(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Accepts multipart document or image upload.
    Stores the raw file separately via StorageService (local now, S3 capable).
    Parses documents (PDF/DOCX/TXT) or prepares images for direct multimodal model ingestion.
    """
    file_bytes = await file.read()
    if len(file_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds maximum 25MB limit.")
        
    user_id = str(current_user.id)
    if not session_id:
        from app.brain.orchestrator import get_working_memory
        wm = get_working_memory(user_id)
        session_id = wm.current_session_id

    try:
        parsed = DocumentParserService.parse_document(file_bytes, file.filename, file.content_type)
    except Exception as e:
        logger.warning(f"File parsing error for {file.filename}: {e}")
        raise HTTPException(status_code=400, detail=f"File parsing failed: {str(e)}")

    storage_service = get_storage_service()
    saved_meta = await storage_service.save_file(
        user_id=user_id,
        session_id=session_id,
        file_name=file.filename,
        file_bytes=file_bytes
    )

    attachment_id = uuid.UUID(saved_meta["file_id"])
    doc_att = DocumentAttachment(
        id=attachment_id,
        user_id=user_id,
        session_id=session_id,
        file_name=saved_meta["file_name"],
        file_type=parsed["file_type"],
        file_size=saved_meta["file_size"],
        storage_path=saved_meta["storage_path"],
        extracted_text=parsed["extracted_text"],
        is_image=parsed["is_image"]
    )
    db.add(doc_att)
    await db.commit()

    return {
        "id": str(doc_att.id),
        "file_name": doc_att.file_name,
        "file_type": doc_att.file_type,
        "file_size": doc_att.file_size,
        "is_image": doc_att.is_image,
        "preview_text": parsed["preview_text"]
    }

@router.get("/chat/attachments/{attachment_id}")
async def get_attachment_file(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Serves the raw attachment content for viewing or download."""
    try:
        att_uuid = uuid.UUID(attachment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid attachment UUID.")
        
    stmt = select(DocumentAttachment).where(
        DocumentAttachment.id == att_uuid,
        DocumentAttachment.user_id == str(current_user.id)
    )
    res = await db.execute(stmt)
    att = res.scalars().first()
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    storage_service = get_storage_service()
    try:
        file_bytes = await storage_service.get_file_bytes(att.storage_path)
    except Exception as e:
        logger.error(f"Error fetching attachment file {att.storage_path}: {e}")
        raise HTTPException(status_code=404, detail="Attachment file not found in storage.")

    return Response(content=file_bytes, media_type=att.file_type)

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Synchronous/REST chat endpoint for testing and client requests.
    Executes the complete cognitive loop via the CognitiveOrchestrator.
    """
    att_meta = await _get_attachments_meta(db, str(current_user.id), req.attachment_ids)
    orchestrator = CognitiveOrchestrator(db)
    result = await orchestrator.step(
        user_id=str(current_user.id),
        prompt=req.prompt,
        attachment_ids=req.attachment_ids
    )
    
    # Log to ChatMessage table for UI history
    now_u = datetime.now(timezone.utc)
    now_a = datetime.now(timezone.utc)
    user_msg = ChatMessage(
        user_id=str(current_user.id),
        session_id=result["session_id"],
        role="user",
        content=req.prompt,
        attachments=att_meta,
        created_at=now_u
    )
    asst_msg = ChatMessage(
        user_id=str(current_user.id),
        session_id=result["session_id"],
        role="assistant",
        content=result["response"],
        cognitive_trace=result.get("cognitive_trace"),
        created_at=now_a
    )
    db.add_all([user_msg, asst_msg])
    await db.commit()
    
    return result

import re

def _clean_title(text: str) -> str:
    """Cleans a string into a concise, readable 2-4 word title without dangling prepositions."""
    words = text.strip().split()
    if len(words) > 4:
        words = words[:4]
    
    # Strip trailing stopwords/prepositions/pronouns
    STOPWORDS = {"in", "on", "at", "for", "with", "about", "to", "of", "and", "the", "a", "an", "su", "by", "or", "from", "which", "that", "i", "we", "you", "it", "am", "is", "are", "was", "were"}
    while words and words[-1].lower().rstrip(".,:;-") in STOPWORDS:
        words.pop()

    title = " ".join(words).strip().rstrip(".,:;-")
    if title:
        title = " ".join([w[0].upper() + w[1:].lower() if len(w) > 0 else "" for w in title.split()])
    return title[:36]

def _generate_chat_title(ep_summary: Optional[str], user_messages: List[str]) -> str:
    """Extracts a short, natural topic title directly related to what was discussed."""
    GREETINGS_PATTERN = r'^(hello|hi|hey|good\s+(morning|afternoon|evening)|hola|yo)\b[,\.!\s]*'
    META_PATTERN = r'\b(already shared|shared you|shared with you|tell me about|what did|what was|remember|recall|can you answer|keep talking|list all|how many|not any specific|what about|as i said|as i told|want to know more about you|who are you)\b'
    LEAD_IN_PATTERN = r'^(my name is\s+\w+\s*\w*|i have\s+|i am\s+(currently\s+)?(working on\s+|building\s+)?|i was\s+|it was\s+|its\s+|can you\s+|could you\s+|please\s+|tell me about\s+|what is\s+|how to\s+|i want to\s+|i am looking for\s+|i like to work on\s+|a\s+|an\s+|the\s+|my\s+|our\s+)+'
    
    # 1. Inspect user turns to find substantive topic intent
    substantive = []
    for msg in user_messages:
        cleaned = re.sub(GREETINGS_PATTERN, '', msg.strip(), flags=re.IGNORECASE).strip()
        if re.search(META_PATTERN, cleaned, flags=re.IGNORECASE):
            continue
        cleaned = re.sub(LEAD_IN_PATTERN, '', cleaned, flags=re.IGNORECASE).strip()
        if len(cleaned.split()) >= 2 and cleaned.lower() not in {"thank you", "thanks", "ok", "okay", "yes", "no"}:
            substantive.append(cleaned)

    # 2. If a substantive user turn exists, it's the most direct topic indicator
    if substantive:
        return _clean_title(substantive[0])

    # 3. If an Episode summary exists, strip clinical third-person phrasing
    if ep_summary:
        prefix_pattern = (
            r'^(the user\s+(was seeking information about|inquired about their current work,\s*which involves|'
            r'inquired about|discussed|was asking about|wanted to know about|shared that they are|'
            r'shared|explained|talked about|requested|asked for|inquired regarding)|'
            r'inquiry regarding|discussion regarding|discussion about|questions regarding)\s+'
        )
        cleaned_ep = re.sub(prefix_pattern, '', ep_summary.strip(), flags=re.IGNORECASE).strip()
        first_clause = re.split(r'[,.]', cleaned_ep)[0].strip()
        if len(first_clause) >= 5:
            return _clean_title(first_clause)

    # 4. Fallback: first user message or default
    if user_messages:
        first = re.sub(GREETINGS_PATTERN, '', user_messages[0].strip(), flags=re.IGNORECASE).strip()
        if first and len(first.split()) >= 1:
            return _clean_title(first)
        return "Greeting & Chat"

    return "New Conversation"

@router.get("/chat/sessions")
async def get_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns a list of distinct sessions for the user with dynamic titles and timestamps."""
    stmt = (
        select(
            ChatMessage.session_id,
            func.max(ChatMessage.created_at).label("last_activity"),
            func.count(ChatMessage.id).label("message_count")
        )
        .where(ChatMessage.user_id == str(current_user.id))
        .group_by(ChatMessage.session_id)
        .order_by(desc("last_activity"))
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 1. Fetch user messages for each session to extract clean contextual titles
    user_msgs_stmt = (
        select(ChatMessage.session_id, ChatMessage.content)
        .where(
            ChatMessage.user_id == str(current_user.id),
            ChatMessage.role == "user"
        )
        .order_by(ChatMessage.created_at.asc())
    )
    user_msgs_res = await db.execute(user_msgs_stmt)
    user_msgs_map: Dict[str, List[str]] = {}
    for sid, content in user_msgs_res.all():
        if content and content.strip():
            if sid not in user_msgs_map:
                user_msgs_map[sid] = []
            user_msgs_map[sid].append(content.strip())

    # 2. Check if a consolidated Episode summary exists for sessions that have closed
    ep_stmt = select(Episode.session_id, Episode.raw_summary).where(Episode.user_id == str(current_user.id))
    ep_res = await db.execute(ep_stmt)
    ep_map = {sid: summary for sid, summary in ep_res.all() if summary}

    sessions = []
    for row in rows:
        sid = row.session_id
        ep_summary = ep_map.get(sid)
        u_msgs = user_msgs_map.get(sid, [])
        title = _generate_chat_title(ep_summary, u_msgs)

        sessions.append({
            "session_id": sid,
            "last_activity": row.last_activity.isoformat() if row.last_activity else None,
            "message_count": row.message_count,
            "title": title
        })
    return sessions

@router.get("/chat/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns the message history for a specific session in strict chronological order."""
    stmt = select(ChatMessage).where(
        ChatMessage.user_id == str(current_user.id),
        ChatMessage.session_id == session_id
    ).order_by(
        ChatMessage.created_at.asc(),
        case((ChatMessage.role == 'user', 0), else_=1),
        ChatMessage.id.asc()
    )
    
    result = await db.execute(stmt)
    messages = []
    for row in result.scalars():
        messages.append({
            "id": str(row.id),
            "role": row.role,
            "content": row.content,
            "cognitive_trace": row.cognitive_trace,
            "attachments": row.attachments,
            "created_at": row.created_at.isoformat() if row.created_at else None
        })
    return messages

@router.post("/chat/sessions/new")
async def start_new_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Instantly starts a new session for the user and consolidates the previous session in background."""
    from app.brain.orchestrator import _active_working_memories, get_working_memory
    from app.workers.tasks import consolidate_session_task

    user_id = str(current_user.id)
    wm = get_working_memory(user_id)
    
    # If prior working memory has messages, dispatch background consolidation asynchronously
    if wm.messages:
        expired_transcript = "\n".join([f"{m.role}: {m.content}" for m in wm.messages])
        expired_session_id = wm.current_session_id
        turn_count = len(wm.messages)
        session_timestamp = wm.messages[0].timestamp if wm.messages else None
        try:
            consolidate_session_task.delay(
                user_id=user_id,
                session_id=expired_session_id,
                transcript=expired_transcript,
                turn_count=turn_count,
                session_timestamp=session_timestamp
            )
        except Exception as e:
            logger.warning(f"Could not dispatch async consolidation task: {e}")

    # Immediately allocate fresh session
    new_session_id = str(uuid.uuid4())
    wm.current_session_id = new_session_id
    wm.messages = []
        
    return {"status": "success", "session_id": new_session_id, "message": "New session started."}

@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...)
):
    """
    Authenticated WebSocket streaming endpoint.
    Requires valid JWT token query parameter.
    Streams real-time LLM token chunks to the client.
    """
    await websocket.accept()
    
    # 1. Authenticate user from JWT token
    async with AsyncSessionLocal() as db:
        user = await get_user_from_token(token, db)
        if not user:
            await websocket.send_json({"error": "Authentication failed or account pending deletion."})
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        user_id = str(user.id)

    try:
        while True:
            data = await websocket.receive_json()
            prompt = data.get("prompt") or data.get("content")
            attachment_ids = data.get("attachment_ids") or []
            if not prompt and not attachment_ids:
                await websocket.send_json({"error": "Prompt or attachments required."})
                continue

            if not prompt:
                prompt = "Please process the attached file(s)."

            # Record user message immediately with current UTC timestamp
            now_user = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                from app.brain.orchestrator import get_working_memory
                wm = get_working_memory(user_id)
                current_sid = wm.current_session_id
                att_meta = await _get_attachments_meta(db, user_id, attachment_ids) if attachment_ids else None
                user_msg = ChatMessage(
                    user_id=user_id,
                    session_id=current_sid,
                    role="user",
                    content=prompt,
                    attachments=att_meta,
                    created_at=now_user
                )
                db.add(user_msg)
                await db.commit()

            # Stream response chunks from the cognitive orchestrator
            async with AsyncSessionLocal() as db:
                orchestrator = CognitiveOrchestrator(db)
                final_event = None

                async for event in orchestrator.step_stream(user_id=user_id, prompt=prompt, attachment_ids=attachment_ids):
                    await websocket.send_json(event)
                    if event.get("type") == "done":
                        final_event = event

                # Record assistant response upon completion
                if final_event:
                    now_asst = datetime.now(timezone.utc)
                    asst_msg = ChatMessage(
                        user_id=user_id,
                        session_id=final_event["session_id"],
                        role="assistant",
                        content=final_event["response"],
                        cognitive_trace=final_event.get("cognitive_trace"),
                        created_at=now_asst
                    )
                    db.add(asst_msg)
                    await db.commit()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            logger.error(f"WebSocket error: {e}")
            await websocket.send_json({"error": str(e)})
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
