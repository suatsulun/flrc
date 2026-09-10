import { Segmented } from "#components/segmented";

const LANGUAGES = [
  { value: "tr", label: "TR", title: "Türkçe" },
  { value: "en", label: "EN", title: "English" },
  { value: "de", label: "DE", title: "Deutsch" },
  { value: "fr", label: "FR", title: "Français" },
] as const;

export function LanguageSwitch({
  language,
  onChange,
  ariaLabel,
}: {
  language: string;
  onChange: (language: string) => void;
  ariaLabel: string;
}) {
  return (
    <Segmented
      ariaLabel={ariaLabel}
      options={LANGUAGES}
      size="sm"
      value={LANGUAGES.find((item) => language.startsWith(item.value))?.value ?? "tr"}
      onChange={onChange}
    />
  );
}
