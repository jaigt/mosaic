from pydantic import BaseModel, Field
from typing import Literal, Optional


class DocumentChunk(BaseModel):
    chunk_id: str
    ticker: str = Field(..., description="Stock ticker symbol, e.g., AAPL")
    cik: str = Field(..., description="SEC CIK number")
    document_type: Literal["10-K", "10-Q", "8-K"]
    filing_year: int
    filing_quarter: Literal["Q1", "Q2", "Q3", "Q4", "FY"]
    sec_item_section: str = Field(..., description="e.g., 'Item 7: MD&A'")
    chunk_type: Literal["text", "table", "chart"]
    text_content: str = Field(..., description="Text or LLM-generated table summary to be embedded")
    raw_payload: str = Field(..., description="Raw HTML/Markdown of the table, or raw text snippet")


class QueryRequest(BaseModel):
    query: str
    ticker: Optional[str] = None
    year: Optional[int] = None
    document_type: Optional[Literal["10-K", "10-Q", "8-K"]] = None
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievedChunk(BaseModel):
    chunk: DocumentChunk
    score: float


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] = Field(default_factory=list)
    ticker: Optional[str] = None
    year: Optional[int] = None
    document_type: Optional[Literal["10-K", "10-Q", "8-K"]] = None


class IngestRequest(BaseModel):
    ticker: str
    document_type: Literal["10-K", "10-Q"] = "10-K"
    year: Optional[int] = None  # None = latest available
