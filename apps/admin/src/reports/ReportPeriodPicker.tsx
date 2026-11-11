import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CalendarDaysIcon } from "lucide-react";
import { Button } from "@flrc/ui/components/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@flrc/ui/components/dialog";
import type { ReportPeriod } from "./report-requests";

function MonthPicker({
  label,
  month,
  onChange,
  disabled,
}: {
  label: string;
  month: number;
  onChange: (month: number) => void;
  disabled: boolean;
}) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const formatter = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    month: "long",
    timeZone: "UTC",
  });
  const months = Array.from({ length: 12 }, (_, index) =>
    formatter.format(new Date(Date.UTC(2024, index, 1))),
  );

  return (
    <div className="grid min-w-0 gap-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger
          render={<Button variant="outline" className="w-full justify-start" />}
          disabled={disabled}
          aria-label={`${label}: ${months[month - 1]}`}
        >
          <CalendarDaysIcon />
          {months[month - 1]}
        </DialogTrigger>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>{label}</DialogTitle>
            <DialogDescription>{t("reports.period.chooseMonth")}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-3 gap-2">
            {months.map((name, index) => (
              <Button
                key={index}
                variant={month === index + 1 ? "default" : "outline"}
                className="h-12 min-w-0 px-1 text-xs"
                aria-pressed={month === index + 1}
                onClick={() => {
                  onChange(index + 1);
                  setOpen(false);
                }}
              >
                {name}
              </Button>
            ))}
          </div>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>{t("forms.cancel")}</DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function ReportPeriodPicker({
  value,
  onChange,
  disabled,
}: {
  value: ReportPeriod;
  onChange: (period: ReportPeriod) => void;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-2 text-sm font-medium">{t("reports.period.label")}</legend>
      <div className="grid grid-cols-2 gap-3">
        <MonthPicker
          label={t("reports.period.startMonth")}
          month={value.startMonth}
          onChange={(startMonth) => onChange({ ...value, startMonth })}
          disabled={disabled}
        />
        <MonthPicker
          label={t("reports.period.endMonth")}
          month={value.endMonth}
          onChange={(endMonth) => onChange({ ...value, endMonth })}
          disabled={disabled}
        />
      </div>
      <p className="text-xs leading-5 text-muted-foreground">{t("reports.period.hint")}</p>
    </fieldset>
  );
}
