from pydantic import BaseModel


class TalentSearchInput(BaseModel):
    query: str
    limit: int = 5
    pool_id: int | None = None


class TalentSearchResult(BaseModel):
    id: int
    name: str
    title: str | None
    company: str | None
    city: str | None
    experience_years: float | None
    salary_expectation: float | None
    match_score: float
    match_summary: str


class TalentSearchOutput(BaseModel):
    results: list[TalentSearchResult]
    total_found: int
    session_id: str


class TalentDetailInput(BaseModel):
    candidate_id: int


class TalentDetailOutput(BaseModel):
    id: int
    name: str
    phone: str | None
    email: str | None
    city: str | None
    current_company: str | None
    current_title: str | None
    years_of_experience: float | None
    expected_salary: float | None
    skills: list[str]
    summary: str | None
    tags: list[str]
