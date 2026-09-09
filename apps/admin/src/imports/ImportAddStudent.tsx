import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { ImportStudentAdd, PreviewClass } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Input } from "@flrc/ui/components/input";
import { NativeSelect } from "@flrc/ui/components/native-select";

export function ImportAddStudent({
  classes,
  initialClass,
  busy,
  onAdd,
  onClose,
}: {
  classes: PreviewClass[];
  initialClass: string;
  busy: boolean;
  onAdd: (student: ImportStudentAdd) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [number, setNumber] = useState("");
  const [name, setName] = useState("");
  const [schoolClass, setSchoolClass] = useState(initialClass);
  const [language, setLanguage] = useState<"german" | "french" | "">("");
  const grade = Number(schoolClass.split("/")[0]);
  function submit(event: FormEvent) {
    event.preventDefault();
    const selected = classes.find((c) => `${c.grade_level}/${c.section}` === schoolClass);
    if (!selected || name.trim().length < 2 || busy) return;
    onAdd({
      school_number: Number(number),
      full_name: name.trim(),
      grade_level: selected.grade_level,
      section: selected.section,
      language: grade >= 4 ? language || null : null,
    });
  }
  return (
    <form
      onSubmit={submit}
      aria-label={t("import.addStudent")}
      className="space-y-3 rounded-lg border border-primary/25 bg-accent/30 p-3"
    >
      <p className="text-sm font-medium">{t("import.addStudent")}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <Input
          autoFocus
          type="number"
          min="1"
          step="1"
          required
          value={number}
          onChange={(e) => setNumber(e.target.value)}
          aria-label={t("students.schoolNumber")}
          placeholder={t("students.schoolNumber")}
          disabled={busy}
        />
        <Input
          required
          minLength={2}
          maxLength={160}
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-label={t("students.fullName")}
          placeholder={t("students.fullName")}
          disabled={busy}
        />
        <NativeSelect
          required
          value={schoolClass}
          onChange={(e) => setSchoolClass(e.target.value)}
          aria-label={t("import.addStudentClass")}
          disabled={busy}
        >
          {classes.map((c) => (
            <option key={`${c.grade_level}/${c.section}`} value={`${c.grade_level}/${c.section}`}>
              {c.grade_level}/{c.section}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          value={grade >= 4 ? language : ""}
          onChange={(e) => setLanguage(e.target.value as typeof language)}
          aria-label={t("roster.language")}
          disabled={busy || grade < 4}
        >
          <option value="">{t("import.noLanguage")}</option>
          <option value="german">{t("subjects.german")}</option>
          <option value="french">{t("subjects.french")}</option>
        </NativeSelect>
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>
          {t("import.addStudent")}
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("forms.cancel")}
        </Button>
      </div>
    </form>
  );
}
