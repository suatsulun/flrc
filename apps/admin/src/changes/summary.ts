import type { TFunction } from "i18next";
import { gradeLabel } from "@flrc/i18n";
import type { AdminActionOut } from "@flrc/api-client";
import { parseUtc } from "../dashboard/format";

type Params = AdminActionOut["params"];

/** Names listed before "+N more", so a bulk change stays one readable line. */
const SHOWN_NAMES = 3;
const SHOWN_EDITS = 3;

function text(value: unknown): string | undefined {
  if (typeof value === "string" && value !== "") return value;
  if (typeof value === "number") return String(value);
  return undefined;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** When a change was made or undone, in the reader's language (the API sends naive UTC). */
export function formatChangeTime(value: string, language: string): string {
  return parseUtc(value).toLocaleString(language, { dateStyle: "short", timeStyle: "short" });
}

/** The first `limit` items, then "+N more" so a bulk change stays one readable line. */
function shortList(
  t: TFunction,
  items: string[],
  { limit, separator, moreKey }: { limit: number; separator: string; moreKey: string },
): string {
  const shown = items.slice(0, limit).join(separator);
  const hidden = items.length - limit;
  return hidden > 0 ? `${shown} ${t(moreKey, { count: hidden })}` : shown;
}

function names(t: TFunction, value: unknown): string {
  const all = list(value).flatMap((item) => text(item) ?? []);
  return shortList(t, all, { limit: SHOWN_NAMES, separator: ", ", moreKey: "changes.more" });
}

function subject(t: TFunction, value: unknown): string {
  const code = text(value);
  return code ? t(`subjects.${code}`, { defaultValue: code }) : "—";
}

/** `8. sınıf · İngilizce`: which grade's fields of which subject a field change touched. */
function scope(t: TFunction, gradeLevel: unknown, subjectCode: unknown): string {
  return t("changes.scope", {
    grade: typeof gradeLevel === "number" ? gradeLabel(t, gradeLevel) : "—",
    subject: subject(t, subjectCode),
  });
}

/** A recorded value in words: booleans, codes and empty values read like the forms show them. */
function value(t: TFunction, field: string, raw: unknown): string {
  if (raw === null || raw === undefined || raw === "") return t("changes.emptyValue");
  if (typeof raw === "boolean") {
    if (field === "is_active") return raw ? t("users.active") : t("users.inactive");
    return raw ? t("changes.yes") : t("changes.no");
  }
  const code = String(raw);
  if (field === "language" || field === "teaching_field") {
    return t(`subjects.${code}`, { defaultValue: code });
  }
  if (field === "teaching_stage") return t(`teachingStages.${code}`, { defaultValue: code });
  if (field === "value_type") return t(`columns.valueTypes.${code}`, { defaultValue: code });
  if (field === "owner_role") return t(`roles.${code}`, { defaultValue: code });
  return code;
}

/** `ad: Ali → Ali Can; okul numarası: 12 → 13` from the API's `{field, from, to}` entries. */
function edits(t: TFunction, changes: unknown, extra: string[] = []): string {
  const items = list(changes).map((entry) => {
    const item = record(entry);
    const field = text(item.field) ?? "";
    return t("changes.editItem", {
      field: t(`changes.fields.${field}`, { defaultValue: field }),
      from: value(t, field, item.from),
      to: value(t, field, item.to),
    });
  });
  return shortList(t, [...items, ...extra], {
    limit: SHOWN_EDITS,
    separator: "; ",
    moreKey: "changes.moreChanges",
  });
}

/** `8/A Sınıf öğretmeni: Ayşe Kaya → Mehmet Demir` per changed teaching slot. */
function slots(t: TFunction, changes: unknown): string {
  const items = list(changes).map((entry) => {
    const item = record(entry);
    const role = text(item.role);
    return t("changes.slotItem", {
      class: text(item.class) ?? "—",
      role: role ? t(`roles.${role}`, { defaultValue: role }) : "—",
      from: text(item.from_teacher) ?? t("changes.nobody"),
      to: text(item.to_teacher) ?? t("changes.nobody"),
    });
  });
  return shortList(t, items, {
    limit: SHOWN_EDITS,
    separator: "; ",
    moreKey: "changes.moreChanges",
  });
}

/**
 * One line describing a recorded admin change, built from the display names the API kept
 * when the change was made (ADR-075), e.g. "Ali Yılmaz 8/A → 8/B taşındı".
 */
export function changeSummary(t: TFunction, action: Pick<AdminActionOut, "kind" | "params">) {
  const params: Params = action.params;
  const student = text(params.student) ?? "—";
  const schoolClass = text(params.class) ?? "—";
  const field = text(params.field) ?? "—";
  const user = text(params.user) ?? "—";
  switch (action.kind) {
    case "student.add":
    case "student.remove":
      return t(`changes.kinds.${action.kind}`, { student, class: schoolClass });
    case "student.move":
      return t("changes.kinds.student.move", {
        students: names(t, params.students),
        from:
          list(params.from_classes)
            .flatMap((item) => text(item) ?? [])
            .join(", ") || "—",
        to: text(params.to_class) ?? "—",
      });
    case "student.edit":
      return t("changes.kinds.student.edit", {
        student,
        class: schoolClass,
        changes: edits(t, params.changes),
      });
    case "student.language": {
      const language = text(params.language);
      return t("changes.kinds.student.language", {
        context: language ? undefined : "none",
        language: language ? subject(t, language) : "",
        students: names(t, params.students),
      });
    }
    case "class.create":
    case "class.delete":
      return t(`changes.kinds.${action.kind}`, { class: schoolClass });
    case "class.edit":
      return t("changes.kinds.class.edit", {
        class: schoolClass,
        previous: text(params.previous_class) ?? "—",
      });
    case "field.create":
    case "field.reorder":
      return t(`changes.kinds.${action.kind}`, {
        field,
        scope: scope(t, params.grade_level, params.subject),
      });
    case "field.delete":
      return t("changes.kinds.field.delete", {
        context: params.disabled === true ? "hidden" : undefined,
        field,
        scope: scope(t, params.grade_level, params.subject),
      });
    case "field.edit":
      return t("changes.kinds.field.edit", {
        field,
        scope: scope(t, params.grade_level, params.subject),
        changes: edits(t, params.changes),
      });
    case "field.copy":
      return t("changes.kinds.field.copy", {
        count: typeof params.count === "number" ? params.count : 0,
        from: scope(t, params.from_grade_level, params.from_subject),
        to: scope(t, params.to_grade_level, params.to_subject),
      });
    case "user.create":
      return t("changes.kinds.user.create", { user, email: text(params.email) ?? "—" });
    case "user.edit":
      return t("changes.kinds.user.edit", {
        user,
        changes: edits(
          t,
          params.changes,
          params.identity_reset === true ? [t("changes.identityReset")] : [],
        ),
      });
    case "signature.upload":
    case "signature.delete":
      return t(`changes.kinds.${action.kind}`, { user });
    case "assignments.replace":
      return t("changes.kinds.assignments.replace", { changes: slots(t, params.changes) });
  }
}
