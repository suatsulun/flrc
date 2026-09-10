from pydantic import BaseModel, Field


class ReportSigner(BaseModel):
    user_id: int
    name: str
    roles: list[str]
    signature: str | None = None


class ReportField(BaseModel):
    """One configured column's label pair and this student's value.

    The printed cards are bilingual documents: Turkish first, the card's own
    language underneath. ``label_alt``/``group_alt`` carry the second language
    and are ``None`` when the school configured no distinct translation.
    """

    label: str
    label_alt: str | None
    group: str | None
    group_alt: str | None
    value_type: str
    value: int | str | None


class ReportCard(BaseModel):
    kind: str
    locale: str
    year_label: str
    semester_number: int
    grade_level: int
    class_name: str
    school_number: int
    student_name: str
    subject: str
    subject_label: str
    fields: list[ReportField]
    average: float | None
    # The middle-school English card carries the student's own second-language
    # score columns as an extra section (the DEUTSCH/FRANÇAIS block).
    language_label: str | None = None
    language_fields: list[ReportField] = Field(default_factory=list)
    teachers: list[ReportSigner] = Field(default_factory=list)
