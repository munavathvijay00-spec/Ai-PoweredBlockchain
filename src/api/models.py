"""
Pydantic response models for the API.
Defines the shape of JSON returned to clients.
"""
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class TransactionResponse(BaseModel):
    """A single transaction as returned by the API."""
    hash: str = Field(..., description="Transaction hash (0x...)")
    from_address: str = Field(..., description="Sender address")
    to_address: str = Field(..., description="Recipient address")
    value_wei: str = Field(..., description="Raw value in wei")
    value_eth: float = Field(..., description="Value in ETH")
    block_number: int = Field(..., description="Block number containing this tx")
    timestamp: datetime = Field(..., description="Block timestamp")
    risk_score: int = Field(..., ge=0, le=100, description="Risk score 0-100")
    ai_explanation: Optional[str] = Field(None, description="AI or deterministic evidence-based explanation")
    explanation_status: str = Field(
        "none",
        description="grounded_ai, deterministic, legacy_unverified, or none",
    )
    risk_factors: List[Dict] = Field(default_factory=list, description="Recorded scoring evidence")
    evidence_assessment: Dict = Field(default_factory=dict, description="Versioned, non-calibrated evidence classification")
    entity_context: Dict = Field(
        default_factory=dict,
        description="Current source-attributed exact-address matches for sender and recipient",
    )
    relationship_context: Dict = Field(
        default_factory=dict,
        description="Descriptive transaction relationship context such as self-transfer and repeated sender-recipient pair counts",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "hash": "0xb73b99073e6a0003db...",
                "from_address": "0x742d35cc6634c0532925a3b844bc454e4438f44e",
                "to_address": "0x0000000000000000000000000000000000000000",
                "value_wei": "249000000000000000000",
                "value_eth": 249.0,
                "block_number": 26056394,
                "timestamp": "2026-09-26T00:26:31",
                "risk_score": 20,
                "ai_explanation": "Evidence-based transaction review: recorded evidence is available.",
                "explanation_status": "deterministic",
                "entity_context": {"sender": [], "recipient": []},
                "relationship_context": {"self_transfer": False, "same_pair_count": 1},
            }
        }


class TransactionListResponse(BaseModel):
    """List of transactions with metadata."""
    transactions: List[TransactionResponse]
    total: int = Field(..., description="Total matching transactions")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Page offset")


class StatsResponse(BaseModel):
    """System-wide statistics with the thresholds used to derive each count."""
    total_transactions: int
    total_addresses: int
    flagged_transactions: int
    flagged_threshold: int = 20
    high_risk_transactions: int = 0
    high_risk_threshold: int = 40
    critical_transactions: int = 0
    critical_threshold: int = 80
    avg_risk_score: float
    max_risk_score: int
    explained_transactions: int
    grounded_explanations: int = 0
    ai_generated_explanations: int = Field(
        0,
        description="Retained rows whose stored explanation passed grounding validation and came from an LLM rewrite",
    )


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str
    database: str
    blockchain: str
