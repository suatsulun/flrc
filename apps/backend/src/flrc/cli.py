from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import typer
from faker import Faker
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from flrc.config import settings
from flrc.db import models as m
from flrc.db.sync import sync_engine
from flrc.modules.academics.programme import L2_START_GRADE, allows_column_type
from flrc.modules.administration.names import normalize_email
from flrc.modules.auth.policy import allowed_google_domain, email_is_in_school_domain
from flrc.modules.imports.fixture import make_hostile_fixture

app = typer.Typer(help="FL-ReportCard maintenance commands. ")

CORE_SECTIONS = ("A", "B", "C", "D", "E", "F")
G_SECTION_GRADES = frozenset({1, 3, 5, 7})
STUDENTS_PER_CLASS = 22
ACADEMIC_YEARS = ("2023-2024", "2024-2025", "2025-2026", "2026-2027")

PRIMARY_ENGLISH_KEYS = tuple(f"primary-{number:02d}" for number in range(1, 13))
SECONDARY_ENGLISH_KEYS = (
    "my-account",
    *(f"secondary-{number:02d}" for number in range(1, 12)),
)
GERMAN_KEYS = ("german-01", "german-02")
FRENCH_KEYS = ("french-01", "french-02")


@dataclass(frozen=True)
class SeedClassPlan:
    grade_level: int
    section: str
    main_teacher: str
    skills_teacher: str
    german_teacher: str | None
    french_teacher: str | None


def sections_for_grade(grade_level: int) -> tuple[str, ...]:
    if grade_level in G_SECTION_GRADES:
        return (*CORE_SECTIONS, "G")
    return CORE_SECTIONS


def seed_class_plans() -> list[SeedClassPlan]:
    """Return a deterministic, school-level-safe teacher allocation."""
    plans: list[SeedClassPlan] = []
    primary_slot = 0
    secondary_slot = 0
    language_slot = 0
    for grade_level in range(1, 9):
        for section in sections_for_grade(grade_level):
            if grade_level <= 4:
                english_pool = PRIMARY_ENGLISH_KEYS
                english_slot = primary_slot
                primary_slot += 1
            else:
                english_pool = SECONDARY_ENGLISH_KEYS
                english_slot = secondary_slot
                secondary_slot += 1
            has_second_language = grade_level >= L2_START_GRADE
            plans.append(
                SeedClassPlan(
                    grade_level=grade_level,
                    section=section,
                    main_teacher=english_pool[english_slot % len(english_pool)],
                    skills_teacher=english_pool[(english_slot + 1) % len(english_pool)],
                    german_teacher=(
                        GERMAN_KEYS[language_slot % len(GERMAN_KEYS)]
                        if has_second_language
                        else None
                    ),
                    french_teacher=(
                        FRENCH_KEYS[language_slot % len(FRENCH_KEYS)]
                        if has_second_language
                        else None
                    ),
                )
            )
            if has_second_language:
                language_slot += 1
    return plans


STUDENT_NOTES = (
    "Derslere düzenli katılıyor ve verilen çalışmaları dikkatle tamamlıyor.",
    "Yeni konuları hızlı kavrıyor ve öğrendiklerini etkinliklerde kullanıyor.",
    "Grup çalışmalarında uyumlu, sorumluluk sahibi ve öğrenmeye istekli.",
    "Okuma ve kelime çalışmalarında istikrarlı bir gelişim gösteriyor.",
    "Ödevlerini düzenli takip ediyor; sözlü katılımını artırması faydalı olacaktır.",
    "Yönergeleri dikkatle izliyor ve çalışmalarını özenle tamamlıyor.",
)
REPORT_LABELS = {
    "progress_exam_1": {
        "tr": "Gelişim Sınavı 1",
        "en": "Progress Exam 1",
        "de": "Lernfortschrittstest 1",
        "fr": "Évaluation de progression 1",
    },
    "progress_exam_2": {
        "tr": "Gelişim Sınavı 2",
        "en": "Progress Exam 2",
        "de": "Lernfortschrittstest 2",
        "fr": "Évaluation de progression 2",
    },
    "quiz_1": {
        "tr": "Kısa Sınav 1",
        "en": "Quiz 1",
        "de": "Kurztest 1",
        "fr": "Quiz 1",
    },
    "quiz_2": {
        "tr": "Kısa Sınav 2",
        "en": "Quiz 2",
        "de": "Kurztest 2",
        "fr": "Quiz 2",
    },
    "reader_1": {
        "tr": "Okuma 1",
        "en": "Reader 1",
        "de": "Lektüre 1",
        "fr": "Lecture 1",
    },
    "reader_2": {
        "tr": "Okuma 2",
        "en": "Reader 2",
        "de": "Lektüre 2",
        "fr": "Lecture 2",
    },
    "homework_1": {
        "tr": "Ödev 1",
        "en": "Homework 1",
        "de": "Hausaufgabe 1",
        "fr": "Devoir 1",
    },
    "homework_2": {
        "tr": "Ödev 2",
        "en": "Homework 2",
        "de": "Hausaufgabe 2",
        "fr": "Devoir 2",
    },
    "highlights": {
        "tr": "Öne Çıkanlar",
        "en": "Highlights",
        "de": "Besondere Leistungen",
        "fr": "Points forts",
    },
    "performance_1": {
        "tr": "Performans 1 (Ana Ders)",
        "en": "PRF 1 (Main Course)",
        "de": "Leistung 1 (Hauptkurs)",
        "fr": "Performance 1 (cours principal)",
    },
    "performance_2": {
        "tr": "Performans 2 (Beceri)",
        "en": "PRF 2 (Skills)",
        "de": "Leistung 2 (Fertigkeiten)",
        "fr": "Performance 2 (compétences)",
    },
    "exam_1": {
        "tr": "Sınav 1",
        "en": "Exam 1",
        "de": "Prüfung 1",
        "fr": "Examen 1",
    },
    "exam_2": {
        "tr": "Sınav 2",
        "en": "Exam 2",
        "de": "Prüfung 2",
        "fr": "Examen 2",
    },
    "teacher_comments": {
        "tr": "Öğretmenin görüşleri",
        "en": "Teacher's comments",
        "de": "Ansichten des Lehrers",
        "fr": "Avis du professeur",
    },
}

# Column order follows the printed middle-school English progress card.
ENGLISH_58 = [
    ("progress_exam_1", "main", "score", True),
    ("progress_exam_2", "main", "score", True),
    ("highlights", "main", "score", False),
    ("reader_1", "skills", "score", False),
    ("reader_2", "skills", "score", False),
    ("homework_1", "main", "score", False),
    ("homework_2", "main", "score", False),
    ("quiz_1", "main", "score", False),
    ("quiz_2", "main", "score", False),
    ("performance_1", "main", "score", False),
    ("performance_2", "skills", "score", False),
]

# Second-language score columns count in the average: the middle-school karne
# prints it as the semester grade (DERS NOTU), and the same columns appear on
# the middle-school English card's DEUTSCH/FRANÇAIS block, grouped as
# Klassenarbeiten/Examens and Hausaufgaben/Devoirs like the printed card.
L2_SCORE_ITEMS = [
    ("exam_1", "exams"),
    ("exam_2", "exams"),
    ("homework_1", "homeworks"),
    ("homework_2", "homeworks"),
]
L2_SCORE_GROUPS = {
    "exams": {"tr": "Sınavlar", "en": "Exams", "de": "Klassenarbeiten", "fr": "Examens"},
    "homeworks": {"tr": "Ödevler", "en": "Homework", "de": "Hausaufgaben", "fr": "Devoirs"},
}

# The karne checklists, transcribed row by row from the school's printed
# cards. Each language has its own curriculum wording, so the lists differ.
KARNE_LANGUAGE_CODES = {"german": "de", "french": "fr"}
KARNE_GROUPS = {
    "german": {
        "attitude": {"tr": "Derse Karşı Tutumlar", "de": "Interesse gegenüber dem Unterricht"},
        "listening": {"tr": "Dinleme Anlama", "de": "Hörverstehen"},
        "reading": {"tr": "Okuma Anlama", "de": "Leseverstehen"},
        "speaking": {"tr": "Konuşma", "de": "Sprechen"},
        "writing": {"tr": "Yazma", "de": "Schreiben"},
    },
    "french": {
        "attitude": {"tr": "Derse Karşı Tutumlar", "fr": "Attitudes pendant le cours"},
        "listening": {"tr": "Dinleme Anlama", "fr": "Compréhension Orale"},
        "reading": {"tr": "Okuma Anlama", "fr": "Compréhension Ecrite"},
        "speaking": {"tr": "Konuşma", "fr": "Production Orale"},
        "writing": {"tr": "Yazma", "fr": "Production Ecrite"},
    },
}
KARNE_ROWS = {
    "german": [
        (
            "attitude",
            "Ders içi ve/veya ders dışı etkinliklere istekle ve aktif olarak katılır.",
            "Nimmt am Unterricht und an außerschulischen Aktivitäten aktiv teil.",
        ),
        (
            "attitude",
            "Ders materyallerini zamanında ve eksiksiz getirir.",
            "Bringt die Unterrichtsmaterialien vollständig und pünktlich mit.",
        ),
        (
            "attitude",
            "Verilen ödevleri/çalışma kâğıtlarını düzenli olarak yapar.",
            "Macht die Hausaufgaben und Arbeitsblätter regelmäßig.",
        ),
        (
            "listening",
            "Duyduğu basit yönergeleri anlayabilir.",
            "Versteht einfache Anweisungen des Lehrers.",
        ),
        (
            "listening",
            "Dinlediği kelimeleri tekrar edebilir.",
            "Kann die gehörten Wörter wiederholen.",
        ),
        (
            "reading",
            "Öğrenmiş olduğu sözcükleri yüksek sesle tekrar edebilir.",
            "Kann die erlernten Wörter laut wiederholen.",
        ),
        (
            "reading",
            "Basit sözcüklerle resimleri eşleştirebilir.",
            "Kann einfache Wörter mit Bildern verbinden.",
        ),
        (
            "speaking",
            "Günlük konularda basit konuşmaları başlatabilir.",
            "Kann mit einfachen Sätzen Alltagsgespräche beginnen.",
        ),
        (
            "speaking",
            "Kendini ve üçüncü kişileri basit cümleler ile tanıtabilir.",
            "Kann sich selbst und dritte Personen mit einfachen Sätzen beschreiben.",
        ),
        (
            "writing",
            "Öğrendiği kelimeleri ve cümle kalıplarını yazabilir.",
            "Kann die erlernten Wörter und Sätze schreiben.",
        ),
        (
            "writing",
            "Görsellerin üzerine öğrendiği kelimeleri yazabilir.",
            "Kann im Zusammenhang mit Bildern erlernte Wörter schreiben.",
        ),
    ],
    "french": [
        (
            "attitude",
            "Ders içi ve/veya ders dışı etkinliklere istekle ve aktif olarak katılır.",
            "Participe activement aux activités intérieures / extérieures de la classe.",
        ),
        (
            "attitude",
            "Ders materyallerini zamanında ve eksiksiz getirir.",
            "Participe aux cours en ayant le matériel nécessaire et à temps.",
        ),
        (
            "attitude",
            "Verilen ödevleri / çalışma kağıtlarını düzenli olarak yapar.",
            "Rend régulièrement ses devoirs / ses activités.",
        ),
        (
            "listening",
            "Günlük yaşamla ilgili olarak kaydedilmiş duyuru ve mesajlardaki "
            "basit bilgileri anlayabilir.",
            "Peut comprendre les informations simples de la vie quotidienne "
            "indiquées dans des petites annonces et des messages.",
        ),
        (
            "listening",
            "Verilen yönergeleri dinlediği zaman sorulan veya verilen bilgiyi "
            "anlar, ilgili etkinliği yapabilir.",
            "Peut comprendre la question et faire l'activité en écoutant les "
            "instructions bien formulées.",
        ),
        (
            "reading",
            "Görsellerle zenginleştirilmiş kısa ve basit mesajları anlayabilir.",
            "Peut comprendre les messages courts et simples enrichis avec des images.",
        ),
        (
            "reading",
            "Basit dilde yazılmış kısa metinleri okuyup anlayabilir.",
            "Peut lire et comprendre les textes courts et simples.",
        ),
        (
            "reading",
            "Yeni metinlerde bilinenden hareketle bilinmeyeni bulmayı ve genel "
            "anlamı çıkarmayı bilir.",
            "Peut comprendre le sens d'un nouveau texte à partir des mots "
            "connus et de saisir le sens général.",
        ),
        (
            "speaking",
            "Sınıfta ihtiyaç duyduklarını almak ve sorular sormak için uygun dili kullanabilir.",
            "Peut poser des questions pour exprimer ses besoins et emprunter des objets en classe.",
        ),
        (
            "speaking",
            "Günlük konularda basit konuşmaları başlatır, karşılık verir, soru "
            "ve cevaplar üretebilir.",
            "Peut lancer de courtes conversations quotidiennes, répondre, "
            "reformuler des questions et des réponses.",
        ),
        (
            "writing",
            "Öğrendiği kelime ve cümle kalıplarını ilgili yerlerde kullanabilir.",
            "Peut se servir du vocabulaire et des structures simples vus précédemment.",
        ),
        (
            "writing",
            "Örneklere bakarak bildiği kelime ve fiilleri kullanarak basit cümleler yazabilir.",
            "A l'aide des exemples, peut écrire de nouvelles phrases avec le "
            "vocabulaire et les verbes vus précédemment.",
        ),
    ],
}

# The primary English progress checklist, transcribed from the printed card.
PRIMARY_GROUPS = {
    "attitude": {"tr": "Derse Karşı Tutumlar", "en": "Attitude Towards Lessons"},
    "listening": {"tr": "Dinleme-Anlama", "en": "Listening Comprehension"},
    "reading": {"tr": "Okuma-Anlama", "en": "Reading Comprehension"},
    "speaking": {"tr": "Konuşma", "en": "Speaking"},
    "writing": {"tr": "Yazma", "en": "Writing"},
}
PRIMARY_ROWS = [
    (
        "attitude",
        "Ders içi ve/veya ders dışı etkinliklere istekle ve aktif olarak katılır.",
        "Participates in internal and/or external activities willingly and actively.",
    ),
    (
        "attitude",
        "Verilen ödevleri özenli ve zamanında yapar.",
        "Does homework neatly on time.",
    ),
    (
        "attitude",
        "Ders materyallerine önem verir, zamanında ve eksiksiz getirir.",
        "Attaches importance to the material(s) required for the lesson and "
        "brings them without fail when needed.",
    ),
    (
        "attitude",
        "Sınıfın disiplin ve düzeniyle ilgili kurallarına uyar.",
        "Obeys the classroom rules regarding discipline and neatness.",
    ),
    (
        "attitude",
        "Grup veya ikili çalışmalarda arkadaşlarıyla uyum içerisinde çalışır.",
        "Works in harmony with his/her friends in group and/or pair work.",
    ),
    (
        "listening",
        "Öğretmenin komutlarını anlar ve yerine getirir.",
        "Can understand and follow the instructions of the teacher.",
    ),
    (
        "listening",
        "Basit hikâye ve metinleri anlar ve takip edebilir.",
        "Can understand and follow simple stories and texts.",
    ),
    (
        "listening",
        "Dinleme aktivitesinde istenilen bilgiyi tespit edebilir ve konu ile "
        "ilgili etkinlikleri yapabilir.",
        "Can identify the information needed in the listening activity and do "
        "the necessary activities accordingly.",
    ),
    (
        "reading",
        "Görsellerle desteklenmiş basit hikaye ve metinleri okur, anlar ve takip edebilir.",
        "Can read, understand and follow simple stories and texts which are supported by visuals.",
    ),
    (
        "reading",
        "Okuduğu ile ilgili etkinlikleri yapabilir.",
        "Can do the activities of what (s)he has read.",
    ),
    (
        "speaking",
        "Tek kelime ya da cümlecikler halinde basit soru veya cevaplar üretir.",
        "Can ask simple questions and give simple answers in words or in phrases.",
    ),
    (
        "speaking",
        "Verilen modeli örnek alıp kendisini sözlü olarak ifade edebilir.",
        "Can express himself/herself in speaking according to the model given.",
    ),
    (
        "writing",
        "Öğrendiği kelimeleri ve cümle kalıplarını yazabilir.",
        "Can write the vocabulary and structure which (s)he has learned.",
    ),
    (
        "writing",
        "Verilen modeli örnek alıp kendisini yazılı olarak ifade edebilir.",
        "Can express himself/herself in writing according to the model given.",
    ),
]


def _labels(key: str) -> dict[str, str]:
    return REPORT_LABELS[key]


def _student_note(school_number: int, subject: str) -> str:
    subject_offset = {"english": 0, "german": 2, "french": 4}[subject]
    return STUDENT_NOTES[(school_number + subject_offset) % len(STUDENT_NOTES)]


def _student_value(
    school_number: int, column: m.ColumnDefinition
) -> tuple[int | None, int | None, str | None]:
    subject_offset = {"english": 0, "german": 11, "french": 23}[column.subject]
    basis = school_number + column.position * 7 + subject_offset
    if column.value_type == "score":
        return 55 + basis % 46, None, None
    if column.value_type == "scale3":
        return None, 1 + basis % 3, None
    return None, None, _student_note(school_number, column.subject)


def seed_columns(db: Session, semester_id: int) -> None:
    def add_column(grade_level: int, subject: str, value_type: str, **kwargs: object) -> None:
        if not allows_column_type(grade_level, subject, value_type):
            return
        db.add(
            m.ColumnDefinition(
                semester_id=semester_id,
                grade_level=grade_level,
                subject=subject,
                value_type=value_type,
                **kwargs,
            )
        )

    for grade in range(5, 9):
        for pos, (key, role, vtype, avg) in enumerate(ENGLISH_58, start=1):
            add_column(
                grade_level=grade,
                subject="english",
                value_type=vtype,
                owner_role=role,
                labels=_labels(key),
                counts_in_average=avg,
                position=pos,
            )
    for grade in range(4, 9):
        for lang in ("german", "french"):
            code = KARNE_LANGUAGE_CODES[lang]
            position = 0
            for key, group_key in L2_SCORE_ITEMS:
                position += 1
                add_column(
                    grade_level=grade,
                    subject=lang,
                    value_type="score",
                    owner_role=lang,
                    labels=_labels(key),
                    group_labels=L2_SCORE_GROUPS[group_key],
                    counts_in_average=True,
                    position=position,
                )
            for group_key, turkish, translated in KARNE_ROWS[lang]:
                position += 1
                add_column(
                    grade_level=grade,
                    subject=lang,
                    value_type="scale3",
                    owner_role=lang,
                    labels={"tr": turkish, code: translated},
                    group_labels=KARNE_GROUPS[lang][group_key],
                    position=position,
                )
            add_column(
                grade_level=grade,
                subject=lang,
                value_type="text",
                owner_role=lang,
                labels=_labels("teacher_comments"),
                position=position + 1,
            )
    for grade in range(1, 5):
        position = 0
        for group_key, turkish, english in PRIMARY_ROWS:
            position += 1
            add_column(
                grade_level=grade,
                subject="english",
                value_type="scale3",
                owner_role="main",
                labels={"tr": turkish, "en": english},
                group_labels=PRIMARY_GROUPS[group_key],
                position=position,
            )
        add_column(
            grade_level=grade,
            subject="english",
            value_type="text",
            owner_role="main",
            labels=_labels("teacher_comments"),
            position=position + 1,
        )


@app.command("make-import-fixture")
def make_import_fixture(out: Path = Path("tests/fixtures/roster-hostile.xlsx")) -> None:
    make_hostile_fixture(out)
    typer.echo(f"wrote {out}")


@app.command("bootstrap-admin")
def bootstrap_admin(
    email: str = typer.Option(..., "--email"),
    full_name: str = typer.Option(..., "--name"),
) -> None:
    """Create the first allowlisted admin; later accounts are managed in the admin UI."""
    normalized_email = normalize_email(email)
    if not settings.allowed_google_domain or not email_is_in_school_domain(normalized_email):
        raise typer.BadParameter("email must belong to ALLOWED_GOOGLE_DOMAIN", param_hint="email")
    cleaned_name = full_name.strip()
    if len(cleaned_name) < 2:
        raise typer.BadParameter(
            "full name must contain at least two characters", param_hint="name"
        )

    with Session(sync_engine()) as db:
        existing = db.scalar(select(m.User).where(m.User.email == normalized_email))
        active_admins = list(
            db.scalars(select(m.User).where(m.User.is_admin.is_(True), m.User.is_active.is_(True)))
        )
        if active_admins:
            if (
                len(active_admins) == 1
                and existing is not None
                and active_admins[0].id == existing.id
            ):
                typer.echo(f"admin already bootstrapped: {normalized_email}")
                return
            raise typer.BadParameter(
                "an active admin already exists; use the authenticated admin UI",
                param_hint="email",
            )
        if existing is None:
            existing = m.User(
                email=normalized_email,
                full_name=cleaned_name,
                is_admin=True,
                is_active=True,
                teaching_stage="middle",
            )
            db.add(existing)
        else:
            existing.full_name = cleaned_name
            existing.is_admin = True
            existing.is_active = True
            existing.teaching_field = "english"
            existing.teaching_stage = "middle"
        db.commit()
    typer.echo(f"bootstrapped admin allowlist entry: {normalized_email}")


@app.command()
def reset() -> None:
    """Dev only: delete every row, children before parents."""
    order = (
        m.JobRun,
        m.AuditEntry,
        m.SaveBatch,
        m.OverrideGrant,
        m.GradeValue,
        m.ColumnDefinition,
        m.TeachingAssignment,
        m.StudentLanguage,
        m.Enrollment,
        m.Student,
        m.SchoolClass,
        m.Semester,
        m.AcademicYear,
        m.DemoVisitor,
        m.User,
    )
    with Session(sync_engine()) as db:
        for table in order:
            db.execute(delete(table))
        db.commit()
    typer.echo("wiped")


@app.command("purge-job-outputs")
def purge_job_outputs() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(sync_engine()) as db:
        condition = (m.JobRun.output_expires_at < now, m.JobRun.output_blob.is_not(None))
        count = db.scalar(select(func.count()).select_from(m.JobRun).where(*condition)) or 0
        db.execute(update(m.JobRun).where(*condition).values(output_blob=None))
        db.commit()
    typer.echo(f"purged {count} job outputs")


def _demo_seed_admin(db: Session) -> m.User | None:
    # Concurrent demo starts must check and populate the database one at a time.
    db.execute(text("SELECT pg_advisory_xact_lock(73318026)"))
    if db.scalar(select(m.AcademicYear.id).limit(1)) or db.scalar(select(m.Student.id).limit(1)):
        typer.echo("demo seed skipped: academic data already exists")
        return None
    admins = list(
        db.scalars(select(m.User).where(m.User.is_admin.is_(True), m.User.is_active.is_(True)))
    )
    if not admins:
        # A visitor-only demo (ADR-051) has no allowlisted person; the seed's
        # assignments still need an administrator to belong to. Nobody can log
        # in as this synthetic account: it has no Google binding and visitor
        # mode never consults the allowlist.
        admin = m.User(
            email=f"admin@{allowed_google_domain() or 'example-school.k12.tr'}",
            full_name="Demo Seed Admin",
            is_admin=True,
            is_coordinator=True,
            teaching_field="english",
            teaching_stage="middle",
        )
        db.add(admin)
        db.flush()
        typer.echo("demo seed: created the synthetic seed administrator")
        return admin
    if len(admins) != 1:
        typer.echo("demo seed skipped: requires exactly one existing active admin")
        return None
    admin = admins[0]
    if (
        not email_is_in_school_domain(admin.email)
        or admin.teaching_field != "english"
        or admin.teaching_stage != "middle"
    ):
        typer.echo("demo seed skipped: admin must be a school-domain middle-school English teacher")
        return None
    return admin


@app.command()
def seed(
    seed_value: int = 42,
    my_email: str = "you@yourschool.k12.tr",
    demo: bool = False,
) -> None:
    """Create the fictional school; --demo fills an empty demo using its existing admin."""
    if demo and settings.env != "demo":
        raise typer.BadParameter("--demo requires ENV=demo")
    Faker.seed(seed_value)
    fake = Faker("tr_TR")

    with Session(sync_engine()) as db:
        if demo:
            existing_admin = _demo_seed_admin(db)
            if existing_admin is None:
                return
            me = existing_admin
        else:
            me = m.User(
                email=my_email,
                full_name="Suat Sülün",
                is_admin=True,
                teaching_field="english",
                teaching_stage="middle",
            )
        users_by_key: dict[str, m.User] = {"my-account": me}
        for key in PRIMARY_ENGLISH_KEYS:
            users_by_key[key] = m.User(
                email=f"{key}@example-school.k12.tr",
                full_name=fake.name(),
                teaching_field="english",
                teaching_stage="primary",
            )
        for key in SECONDARY_ENGLISH_KEYS:
            if key == "my-account":
                continue
            users_by_key[key] = m.User(
                email=f"{key}@example-school.k12.tr",
                full_name=fake.name(),
                teaching_field="english",
                teaching_stage="middle",
            )
        for key in GERMAN_KEYS:
            users_by_key[key] = m.User(
                email=f"{key}@example-school.k12.tr",
                full_name=fake.name(),
                teaching_field="german",
                teaching_stage=None,
            )
        for key in FRENCH_KEYS:
            users_by_key[key] = m.User(
                email=f"{key}@example-school.k12.tr",
                full_name=fake.name(),
                teaching_field="french",
                teaching_stage=None,
            )
        db.add_all(users_by_key.values())
        db.flush()

        plans = seed_class_plans()
        previous_rosters: dict[tuple[int, str], list[m.Student]] = {}
        student_count = 0
        enrollment_count = 0
        class_count = 0
        value_count = 0
        note_count = 0
        for year_offset, label in enumerate(ACADEMIC_YEARS):
            is_current = year_offset == len(ACADEMIC_YEARS) - 1
            year = m.AcademicYear(label=label, status="active" if is_current else "archived")
            db.add(year)
            db.flush()
            semesters = [
                m.Semester(
                    year_id=year.id,
                    number=number,
                    status="open" if is_current and number == 1 else "locked",
                )
                for number in (1, 2)
            ]
            db.add_all(semesters)
            db.flush()
            for semester in semesters:
                seed_columns(db, semester.id)
            db.flush()

            columns_by_scope: dict[tuple[int, int, str], list[m.ColumnDefinition]] = {}
            for column in db.scalars(
                select(m.ColumnDefinition)
                .where(m.ColumnDefinition.semester_id.in_([item.id for item in semesters]))
                .order_by(
                    m.ColumnDefinition.semester_id,
                    m.ColumnDefinition.grade_level,
                    m.ColumnDefinition.subject,
                    m.ColumnDefinition.position,
                )
            ):
                columns_by_scope.setdefault(
                    (column.semester_id, column.grade_level, column.subject), []
                ).append(column)

            current_rosters: dict[tuple[int, str], list[m.Student]] = {}
            school_number = 1
            for plan in plans:
                school_class = m.SchoolClass(
                    year_id=year.id,
                    grade_level=plan.grade_level,
                    section=plan.section,
                )
                db.add(school_class)
                db.flush()
                class_count += 1

                role_teachers = {
                    "main": users_by_key[plan.main_teacher],
                    "skills": users_by_key[plan.skills_teacher],
                }
                assignments = [
                    m.TeachingAssignment(
                        class_id=school_class.id,
                        role=role,
                        user_id=teacher.id,
                    )
                    for role, teacher in role_teachers.items()
                ]
                if plan.german_teacher and plan.french_teacher:
                    role_teachers["german"] = users_by_key[plan.german_teacher]
                    role_teachers["french"] = users_by_key[plan.french_teacher]
                    assignments.extend(
                        [
                            m.TeachingAssignment(
                                class_id=school_class.id,
                                role="german",
                                user_id=role_teachers["german"].id,
                            ),
                            m.TeachingAssignment(
                                class_id=school_class.id,
                                role="french",
                                user_id=role_teachers["french"].id,
                            ),
                        ]
                    )
                db.add_all(assignments)

                source_key = (plan.grade_level - 1, plan.section)
                roster = previous_rosters.get(source_key) if plan.grade_level > 1 else None
                if roster is None:
                    roster = []
                    for _ in range(STUDENTS_PER_CLASS):
                        name = fake.name()
                        roster.append(
                            m.Student(
                                full_name=name,
                                search_name=name.casefold(),
                            )
                        )
                    db.add_all(roster)
                    db.flush()
                    student_count += len(roster)
                current_rosters[(plan.grade_level, plan.section)] = roster

                for student_index, student in enumerate(roster):
                    student_number = school_number
                    school_number += 1
                    enrollment_count += 1
                    db.add(
                        m.Enrollment(
                            student_id=student.id,
                            class_id=school_class.id,
                            year_id=year.id,
                            school_number=student_number,
                        )
                    )
                    subjects = ["english"]
                    if plan.grade_level >= L2_START_GRADE:
                        language = "german" if student_index < 14 else "french"
                        db.add(
                            m.StudentLanguage(
                                student_id=student.id,
                                year_id=year.id,
                                language=language,
                            )
                        )
                        subjects.append(language)
                    filled_semesters = semesters[:1] if is_current else semesters
                    for semester in filled_semesters:
                        for subject in subjects:
                            for column in columns_by_scope[
                                (semester.id, plan.grade_level, subject)
                            ]:
                                score, scale, text_value = _student_value(student_number, column)
                                db.add(
                                    m.GradeValue(
                                        student_id=student.id,
                                        column_definition_id=column.id,
                                        score=score,
                                        scale=scale,
                                        text_value=text_value,
                                        updated_by=role_teachers[column.owner_role].id,
                                    )
                                )
                                value_count += 1
                                note_count += text_value is not None
            previous_rosters = current_rosters
        db.commit()
    typer.echo(
        f"seeded: {len(ACADEMIC_YEARS)} years, {class_count} classes, "
        f"{student_count} student identities, {enrollment_count} enrollments, "
        f"{value_count} report-card values ({note_count} comments), "
        f"{len(users_by_key)} teachers"
    )


@app.command("seed-e2e")
def seed_e2e() -> None:
    """Create the tiny deterministic synthetic E2E school."""
    order = (
        m.JobRun,
        m.AuditEntry,
        m.SaveBatch,
        m.OverrideGrant,
        m.GradeValue,
        m.ColumnDefinition,
        m.TeachingAssignment,
        m.StudentLanguage,
        m.Enrollment,
        m.Student,
        m.SchoolClass,
        m.Semester,
        m.AcademicYear,
        m.DemoVisitor,
        m.User,
    )
    with Session(sync_engine()) as db:
        for table in order:
            db.execute(delete(table))
        year = m.AcademicYear(label="E2E Synthetic Year", status="active")
        owner = m.User(
            email="owner@example-school.k12.tr",
            full_name="E2E Owner",
            teaching_stage="middle",
        )
        admin = m.User(
            email="admin@example-school.k12.tr",
            full_name="E2E Admin",
            is_admin=True,
            is_coordinator=True,
            teaching_stage="middle",
        )
        primary_teachers = [
            m.User(
                email=f"primary-{number:02d}@example-school.k12.tr",
                full_name=f"E2E Primary Teacher {number:02d}",
                teaching_stage="primary",
            )
            for number in range(1, 13)
        ]
        middle_teachers = [
            m.User(
                email=f"middle-{number:02d}@example-school.k12.tr",
                full_name=f"E2E Middle Teacher {number:02d}",
                teaching_stage="middle",
            )
            for number in range(1, 11)
        ]
        german_teachers = [
            m.User(
                email=f"german-{number:02d}@example-school.k12.tr",
                full_name=f"E2E German Teacher {number:02d}",
                teaching_field="german",
                teaching_stage=None,
            )
            for number in range(1, 3)
        ]
        french_teachers = [
            m.User(
                email=f"french-{number:02d}@example-school.k12.tr",
                full_name=f"E2E French Teacher {number:02d}",
                teaching_field="french",
                teaching_stage=None,
            )
            for number in range(1, 3)
        ]
        setup_year = m.AcademicYear(label="2027-2028", status="setup")
        db.add_all(
            [
                year,
                setup_year,
                owner,
                admin,
                *primary_teachers,
                *middle_teachers,
                *german_teachers,
                *french_teachers,
            ]
        )
        db.flush()
        semester = m.Semester(year_id=year.id, number=1, status="open")
        second = m.Semester(year_id=year.id, number=2, status="locked")
        setup_semesters = [
            m.Semester(year_id=setup_year.id, number=number, status="locked") for number in (1, 2)
        ]
        school_class = m.SchoolClass(year_id=year.id, grade_level=5, section="A")
        target_class = m.SchoolClass(year_id=year.id, grade_level=5, section="B")
        db.add_all([semester, second, *setup_semesters, school_class, target_class])
        db.flush()
        column = m.ColumnDefinition(
            semester_id=semester.id,
            grade_level=5,
            subject="english",
            value_type="score",
            owner_role="main",
            labels={"tr": "Sınav", "en": "Exam", "de": "Prüfung", "fr": "Examen"},
            counts_in_average=True,
            position=1,
        )
        students = [
            m.Student(
                full_name="E2E Synthetic One",
                search_name="e2e synthetic one",
            ),
            m.Student(
                full_name="E2E Synthetic Two",
                search_name="e2e synthetic two",
            ),
        ]
        db.add_all([column, *students])
        db.flush()
        db.add_all(
            [
                m.TeachingAssignment(class_id=school_class.id, role="main", user_id=owner.id),
                m.TeachingAssignment(class_id=target_class.id, role="main", user_id=owner.id),
            ]
        )
        db.add_all(
            [
                m.Enrollment(
                    student_id=item.id,
                    year_id=year.id,
                    class_id=school_class.id,
                    school_number=99001 + index,
                )
                for index, item in enumerate(students)
            ]
        )
        db.commit()
        typer.echo(
            f"seeded e2e class={school_class.id} student={students[0].id} column={column.id}"
        )
