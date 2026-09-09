import { useTranslation } from "react-i18next";
import { i18n } from "@flrc/i18n";
import { Segmented } from "@flrc/ui/components/segmented";

const LANGUAGES = [
  { value: "tr", label: "TR", title: "Türkçe" },
  { value: "en", label: "EN", title: "English" },
  { value: "de", label: "DE", title: "Deutsch" },
  { value: "fr", label: "FR", title: "Français" },
] as const;

export function LanguageSwitch() {
  const { t, i18n: instance } = useTranslation();
  return (
    <Segmented
      ariaLabel={t("shell.language")}
      options={LANGUAGES}
      size="sm"
      value={
        (LANGUAGES.find((item) => instance.language.startsWith(item.value))?.value ?? "tr") as "tr"
      }
      onChange={(value) => void i18n.changeLanguage(value)}
    />
  );
}
