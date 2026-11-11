from pydantic import BaseModel, Field


class ReportMonthRange(BaseModel):
    """Months printed on a requested card, independent of its academic semester."""

    start_month: int = Field(ge=1, le=12)
    end_month: int = Field(ge=1, le=12)

    @property
    def label(self) -> str:
        # English card wording is fixed regardless of the interface/report locale.
        months = (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        )
        return f"{months[self.start_month - 1]} - {months[self.end_month - 1]}"


def report_month_range(
    kind: str, start_month: int | None, end_month: int | None
) -> ReportMonthRange | None:
    if start_month is None and end_month is None:
        return None
    if kind != "english_middle" or start_month is None or end_month is None:
        raise ValueError("invalid_report_period")
    return ReportMonthRange(start_month=start_month, end_month=end_month)


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
    report_period: ReportMonthRange | None = None
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
    language_subject: str | None = None
    language_label: str | None = None
    language_fields: list[ReportField] = Field(default_factory=list)
    teachers: list[ReportSigner] = Field(default_factory=list)
