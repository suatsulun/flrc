import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { listStudentsOptions } from "@flrc/api-client";
import { Button } from "@flrc/ui/components/button";
import { Input } from "@flrc/ui/components/input";
import { Skeleton } from "@flrc/ui/components/skeleton";
import { XIcon } from "lucide-react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useDebouncedValue } from "./use-debounced-value";

const SUGGESTIONS = 8;

export type PickedStudent = { id: number; name: string };

/**
 * Finds one student by name or school number and hands back their id; shows the choice as a
 * removable chip. Searches the current year, like the student search page's default.
 */
export function StudentPicker({
  id,
  value,
  onChange,
  className,
}: {
  id?: string;
  value: PickedStudent | undefined;
  onChange: (student: PickedStudent | undefined) => void;
  className?: string;
}) {
  const { t } = useTranslation();
  const listId = useId();
  const [text, setText] = useState("");
  const q = useDebouncedValue(text.trim());
  const { data, isFetching } = useQuery({
    ...listStudentsOptions({ query: { q, limit: SUGGESTIONS } }),
    enabled: !value && q.length > 0,
    placeholderData: keepPreviousData,
  });
  const matches = q ? (data?.items ?? []) : [];

  if (value) {
    return (
      <span
        className={`inline-flex h-9 max-w-full items-center gap-1 rounded-lg border border-input bg-card pr-1 pl-3 text-sm shadow-card ${className ?? ""}`}
      >
        <span className="truncate" title={value.name}>
          {value.name}
        </span>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label={t("audit.clearStudent")}
          onClick={() => onChange(undefined)}
        >
          <XIcon />
        </Button>
      </span>
    );
  }

  return (
    <div className={`relative ${className ?? ""}`}>
      <Input
        id={id}
        className="h-9 rounded-lg"
        type="search"
        role="combobox"
        aria-expanded={matches.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-label={t("audit.studentFilter")}
        placeholder={t("audit.studentPlaceholder")}
        value={text}
        onChange={(event) => setText(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setText("");
        }}
      />
      {q ? (
        <ul
          id={listId}
          role="listbox"
          aria-label={t("audit.studentFilter")}
          className="absolute top-full right-0 left-0 z-40 mt-1 max-h-72 overflow-auto rounded-lg border border-border bg-popover p-1 shadow-lg"
        >
          {matches.length === 0 && isFetching ? (
            <li className="px-2 py-1">
              <span className="sr-only">{t("loading")}</span>
              {Array.from({ length: 3 }, (_, index) => (
                <div key={index} aria-hidden className="flex items-center gap-2 py-1.5">
                  <Skeleton className="h-3.5 w-10 shrink-0 rounded-md" />
                  <Skeleton className="h-4 flex-1 rounded-md" />
                </div>
              ))}
            </li>
          ) : matches.length === 0 ? (
            <li className="px-2 py-1.5 text-sm text-muted-foreground">
              {t("audit.noStudentMatches")}
            </li>
          ) : (
            matches.map((student) => (
              <li key={student.id} role="option" aria-selected={false}>
                <button
                  type="button"
                  className="flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
                  onClick={() => {
                    onChange({ id: student.id, name: student.full_name });
                    setText("");
                  }}
                >
                  <span className="tabular w-10 shrink-0 text-xs text-muted-foreground">
                    {student.school_number ?? "—"}
                  </span>
                  <span className="truncate">{student.full_name}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
