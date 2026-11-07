import { listClassCatalogOptions } from "@flrc/api-client";
import { EmptyState } from "@flrc/ui/components/empty-state";
import { createFileRoute, redirect } from "@tanstack/react-router";
import { FileTextIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ReportModeSwitch } from "../../class-report/report-mode-switch";
import { defaultReportClass } from "../../class-report/scope";

/**
 * Sınıf raporu without a class: every user may read middle-school English class reports, so this
 * opens the user's own middle-school English class, else the school's first. Only a school year
 * without any such class stays here, on an explanation.
 */
export const Route = createFileRoute("/_auth/class-report/")({
  loader: async ({ context }) => {
    const target = defaultReportClass(
      await context.queryClient.ensureQueryData(listClassCatalogOptions()),
    );
    if (target) {
      throw redirect({
        to: "/class-report/$classId",
        params: { classId: String(target.id) },
        search: { semester: undefined },
        replace: true,
      });
    }
  },
  component: NoClassReport,
});

function NoClassReport() {
  const navigate = Route.useNavigate();
  const { t } = useTranslation();
  return (
    <div className="space-y-4">
      <ReportModeSwitch
        mode="sheet"
        onChange={() =>
          void navigate({
            to: "/card-preview",
            search: {
              semesterId: undefined,
              classId: undefined,
              kind: undefined,
              studentId: undefined,
            },
          })
        }
      />
      <EmptyState
        icon={<FileTextIcon />}
        title={t("classReport.noneTitle")}
        description={t("classReport.noneBody")}
      />
    </div>
  );
}
