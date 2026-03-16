from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProposalStatus = Literal["proposed", "approved", "rejected", "applied"]
ReviewAction = Literal["approve", "reject", "apply"]


class ProposalReviewRecord(BaseModel):
    proposal_id: str = Field(..., min_length=1)
    status: ProposalStatus = "proposed"
    reviewer: str = "system"
    note: str = ""


class ProposalReviewRequest(BaseModel):
    proposal_id: str = Field(..., min_length=1)
    action: ReviewAction
    reviewer: str = "human"
    note: str = ""
