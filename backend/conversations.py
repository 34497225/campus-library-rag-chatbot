import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.database import get_db_session
from backend.dependencies import get_current_user
from backend.models import User
from backend.repositories import (
    create_conversation as create_conversation_record,
    create_message_for_owner,
    delete_conversation_for_owner,
    get_conversation_for_owner,
    list_conversations_for_owner,
    list_messages_for_owner,
    rename_conversation_for_owner,
)
from backend.schemas import (
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
    MessageCreate,
    MessageRead,
)


# 這個 router 中的所有 endpoint 都會以 /conversations 開頭。
# tags 只影響 Swagger /docs 的分組顯示。
router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
)


@router.post(
    "",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation_endpoint(
    payload: ConversationCreate,
    session: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ConversationRead:
    """Create a conversation owned by the authenticated user."""

    # payload 只能提供 title，不能提供 user_id。
    # ConversationCreate 已負責：
    # 1. 去除標題前後空白
    # 2. 阻止空白標題
    # 3. 限制標題長度
    # 4. 拒絕 user_id 等額外欄位

    # 擁有者 ID 只從驗證完成的 current_user 取得。
    # 即使攻擊者知道其他使用者的 UUID，也無法替對方建立對話。
    conversation = create_conversation_record(
        session=session,
        owner_id=current_user.id,
        title=payload.title,
    )

    # ConversationRead 只輸出安全欄位，
    # 不將資料庫中的 user_id 直接暴露給用戶端。
    return ConversationRead.model_validate(conversation)


@router.get(
    "",
    response_model=list[ConversationRead],
)
def list_conversations_endpoint(
    session: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ConversationRead]:
    """Return conversations owned by the authenticated user."""

    # owner_id 只取自 JWT 驗證完成的 current_user。
    # API 不提供 user_id query parameter，避免查詢別人的對話。
    conversations = list_conversations_for_owner(
        session=session,
        owner_id=current_user.id,
    )

    return [
        ConversationRead.model_validate(conversation)
        for conversation in conversations
    ]


@router.get(
    "/{conversation_id}",
    response_model=ConversationRead,
)
def read_conversation_endpoint(
    conversation_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ConversationRead:
    """Return one conversation only when the user owns it."""

    conversation = get_conversation_for_owner(
        session=session,
        conversation_id=conversation_id,
        owner_id=current_user.id,
    )

    # 不存在與不屬於目前使用者都回傳相同 404，
    # 避免透過不同狀態碼枚舉其他使用者的 conversation UUID。
    if conversation is None:
        raise conversation_not_found()

    return ConversationRead.model_validate(conversation)


@router.patch(
    "/{conversation_id}",
    response_model=ConversationRead,
)
def rename_conversation_endpoint(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    session: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ConversationRead:
    """Rename one conversation only when the user owns it."""

    conversation = rename_conversation_for_owner(
        session=session,
        conversation_id=conversation_id,
        owner_id=current_user.id,
        title=payload.title,
    )

    if conversation is None:
        raise conversation_not_found()

    return ConversationRead.model_validate(conversation)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_conversation_endpoint(
    conversation_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Delete one conversation only when the user owns it."""

    deleted = delete_conversation_for_owner(
        session=session,
        conversation_id=conversation_id,
        owner_id=current_user.id,
    )

    if not deleted:
        raise conversation_not_found()

    # 204 的語意是成功，但 response 沒有 body。
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
def create_message_endpoint(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    session: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> MessageRead:
    """Create a user message in an owned conversation."""

    # role 由伺服器固定為 user，而不是從 payload 接收。
    # 未來 assistant 回答會由受信任的後端 RAG 流程寫入。
    message = create_message_for_owner(
        session=session,
        conversation_id=conversation_id,
        owner_id=current_user.id,
        role="user",
        content=payload.content,
    )

    if message is None:
        raise conversation_not_found()

    return MessageRead.model_validate(message)


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageRead],
)
def list_messages_endpoint(
    conversation_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[MessageRead]:
    """Return ordered messages from an owned conversation."""

    messages = list_messages_for_owner(
        session=session,
        conversation_id=conversation_id,
        owner_id=current_user.id,
    )

    # None 表示對話不存在或不可存取；空 list 則表示擁有的對話尚無訊息。
    if messages is None:
        raise conversation_not_found()

    return [MessageRead.model_validate(message) for message in messages]


def conversation_not_found() -> HTTPException:
    """Create the shared response for missing or inaccessible conversations."""

    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Conversation not found.",
    )
