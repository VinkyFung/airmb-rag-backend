from pydantic import BaseModel, Field


class FaqImportIssue(BaseModel):
    level: str
    sheet: str
    row: int | None = None
    field: str | None = None
    message: str


class FaqImportPreviewItem(BaseModel):
    sheet: str
    row: int
    knowledge_id: str
    category_l1: str | None = None
    category_l2: str | None = None
    category_l3: str | None = None
    business_type: str | None = None
    standard_question: str
    paraphrases: list[str] = Field(default_factory=list)
    answer: str
    image_url: str | None = None
    risk_level: int = 0
    auth_required: bool = False
    auto_answer: bool = True
    human_required: bool = False
    status: int = 0
    review_status: int = 0
    blocked: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FaqImportSheetSummary(BaseModel):
    sheet: str
    total_rows: int
    valid_rows: int
    invalid_rows: int


class FaqImportParseData(BaseModel):
    file_name: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    warning_rows: int
    preview_limit: int
    sheets: list[FaqImportSheetSummary]
    items: list[FaqImportPreviewItem]
    issues: list[FaqImportIssue]


class FaqImportConfirmItem(BaseModel):
    sheet: str
    row: int
    knowledge_id: str
    faq_id: int | None = None
    action: str
    success: bool
    message: str


class FaqImportConfirmData(BaseModel):
    file_name: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    created: int
    updated: int
    failed: int
    skipped: int
    status: int
    items: list[FaqImportConfirmItem]
    issues: list[FaqImportIssue]
