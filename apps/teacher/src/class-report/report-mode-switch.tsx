import { Segmented } from "@flrc/ui/components/segmented";
import { useTranslation } from "react-i18next";

export type ReportMode = "sheet" | "preview";

/** "Sınıf raporu | Karne önizleme": the two views of the teacher's class report section. */
export function ReportModeSwitch({
  mode,
  onChange,
}: {
  mode: ReportMode;
  onChange: (mode: ReportMode) => void;
}) {
  const { t } = useTranslation();
  return (
    <Segmented<ReportMode>
      ariaLabel={t("classReport.modeLabel")}
      value={mode}
      onChange={(next) => {
        if (next !== mode) onChange(next);
      }}
      options={[
        { value: "sheet", label: t("classReport.modeSheet") },
        { value: "preview", label: t("classReport.modePreview") },
      ]}
    />
  );
}
