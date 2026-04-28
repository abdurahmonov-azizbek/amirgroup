from sqlalchemy import Column, Integer, String, BigInteger, Enum, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid

from .base import Base

class VerificationStatus(enum.Enum):
    new = "new"
    verification_pending = "verification_pending"
    verified = "verified"
    rejected = "rejected"

class UserStatus(enum.Enum):
    active = "active"
    inactive = "inactive"
    blocked = "blocked"

class UserRole(enum.Enum):
    user = "user"
    auditor = "auditor"
    admin = "admin"

class ReconStatus(enum.Enum):
    pending = "pending"
    processing = "processing"
    failed = "failed"
    cancelled = "cancelled"
    completed = "completed"

class ReconLogStatus(enum.Enum):
    sent = "sent"
    failed = "failed"
    confirmed = "confirmed"
    disowned = "disowned"

class BroadcastLogStatus(enum.Enum):
    sent = "sent"
    failed = "failed"

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    api_uuid = Column(String(36), default=lambda: str(uuid.uuid4()), nullable=True)

    user_id = Column(BigInteger, unique=True, index=True)
    nickname = Column(String, nullable=True)
    username = Column(String, nullable=True)

    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)

    phone_number = Column(String, nullable=True)
    market_name = Column(String, nullable=True)
    region = Column(String, nullable=True)

    passport_front_side = Column(String, nullable=True)
    passport_back_side = Column(String, nullable=True)
    pinfl = Column(String(14), nullable=True)
    selfie_photo = Column(String, nullable=True)

    verification_status = Column(Enum(VerificationStatus), default=VerificationStatus.new)
    verification_group_message_id = Column(Integer, nullable=True)  # Group xabarining message_id
    verification_group_chat_id = Column(BigInteger, nullable=True)  # Group chat_id
    status = Column(Enum(UserStatus), default=UserStatus.active)
    role = Column(Enum(UserRole), default=UserRole.user)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Reconciliation(Base):
    __tablename__ = 'reconciliations'

    id = Column(Integer, primary_key=True, index=True)
    status = Column(Enum(ReconStatus), default=ReconStatus.pending)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    logs = relationship("ReconciliationLog", back_populates="reconciliation")

class ReconciliationLog(Base):
    __tablename__ = 'reconciliation_logs'

    id = Column(Integer, primary_key=True, index=True)
    reconciliation_id = Column(Integer, ForeignKey('reconciliations.id', ondelete='CASCADE'))
    tele_user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    disown_text = Column(String(500), nullable=True)
    status = Column(Enum(ReconLogStatus), default=ReconLogStatus.sent)
    
    total_debt = Column(BigInteger, default=0)
    overdue_debt = Column(BigInteger, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    reconciliation = relationship("Reconciliation", back_populates="logs")
    user = relationship("User")

class Broadcast(Base):
    __tablename__ = 'broadcasts'

    id = Column(Integer, primary_key=True, index=True)
    from_chat_id = Column(BigInteger)
    message_ids = Column(Text)
    reply_markup = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    logs = relationship("BroadcastLog", back_populates="broadcast")

class BroadcastLog(Base):
    __tablename__ = 'broadcast_logs'

    id = Column(Integer, primary_key=True, index=True)
    broadcast_id = Column(Integer, ForeignKey('broadcasts.id', ondelete='CASCADE')) 
    tele_user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
    status = Column(Enum(BroadcastLogStatus), default=BroadcastLogStatus.sent)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    broadcast = relationship("Broadcast", back_populates="logs")
    user = relationship("User")

class Config(Base):
    __tablename__ = 'configs'

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String)
    key = Column(String, unique=True, index=True)
    value = Column(String)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class FSMState(Base):
    __tablename__ = "fsm_states"
    user_id = Column(BigInteger, primary_key=True)
    chat_id = Column(BigInteger, primary_key=True)
    state = Column(String, nullable=True)
    data = Column(String, nullable=True)
