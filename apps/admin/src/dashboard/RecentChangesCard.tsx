import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";
import { ArrowRightIcon } from "lucide-react";
import { listAdminActionsOptions } from "@flrc/api-client";
import { buttonVariants } from "@flrc/ui/components/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@flrc/ui/components/card";
import { ChangeStatusBadge, UndoChangeButton } from "../changes/ChangeControls";
import { changeSummary, formatChangeTime } from "../changes/summary";

const CHANGE_LIMIT = 5;

/** The latest recorded admin changes with Undo; the full list lives on /changes (ADR-075). */
export function RecentChangesCard() {
  const { t, i18n } = useTranslation();
  const { data, isPending, isError, dataUpdatedAt } = useQuery(
    listAdminActionsOptions({ query: { limit: CHANGE_LIMIT } }),
  );
  const items = data?.items ?? [];

  return (
    <Card data-testid="recent-changes-card">
      <CardHeader>
        <div className="min-w-0">
          <CardTitle>{t("changes.title")}</CardTitle>
          <CardDescription>{t("changes.dashboard.description")}</CardDescription>
        </div>
        <Link to="/changes" className={buttonVariants({ variant: "ghost", size: "sm" })}>
          {t("changes.dashboard.viewAll")}
          <ArrowRightIcon />
        </Link>
      </CardHeader>
      {isPending ? (
        <p className="border-t border-border px-5 py-6 text-sm text-muted-foreground">
          {t("loading")}
        </p>
      ) : isError ? (
        <p className="border-t border-border px-5 py-6 text-sm text-muted-foreground">
          {t("errors.load")}
        </p>
      ) : items.length === 0 ? (
        <p className="border-t border-border px-5 py-6 text-sm text-muted-foreground">
          {t("changes.empty")}
        </p>
      ) : (
        <ul className="divide-y divide-border border-t border-border">
          {items.map((action) => (
            <li
              key={action.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-2.5 sm:flex-nowrap"
            >
              <div className="min-w-0 flex-1 basis-full space-y-1 sm:basis-auto">
                <p className="text-sm font-medium">{changeSummary(t, action)}</p>
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                  <span>
                    {action.actor ?? t("changes.unknownActor")} ·{" "}
                    {formatChangeTime(action.created_at, i18n.language)}
                  </span>
                  <ChangeStatusBadge action={action} now={dataUpdatedAt} />
                </p>
              </div>
              {action.status === "available" ? <UndoChangeButton action={action} /> : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
