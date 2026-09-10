import { demoInfoOptions, sessionOptions } from "@flrc/api-client";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@flrc/ui/components/button";
import { Card, CardContent } from "@flrc/ui/components/card";
import { formatClockTime } from "@flrc/ui/components/demo-banner";
import { SchoolLogo } from "@flrc/ui/components/school-logo";

import { LanguageSwitch } from "@flrc/ui/components/language-switch";
import { LOGO_URL, SCHOOL_NAME } from "@flrc/branding";

export const Route = createFileRoute("/login")({
  validateSearch: (s): { error?: string } => ({
    error: typeof s.error === "string" ? s.error : undefined,
  }),
  component: LoginPage,
});

const AUTH_ERROR_CODES = [
  "wrong_domain",
  "not_registered",
  "google_error",
  "email_not_verified",
  "invalid_identity",
  "identity_mismatch",
  "demo_full",
] as const;

/**
 * Sign-in.
 *
 * Deliberately a single centred column with nothing to read: the school's mark,
 * its name, and the one button. Everyone who reaches this page already knows
 * what the product is, so there is nothing here to sell them.
 */
function LoginPage() {
  const { t, i18n } = useTranslation();
  const [signInPending, setSignInPending] = useState(false);
  const { error } = Route.useSearch();
  const { data: user } = useQuery(sessionOptions());
  // Only the public demo serves this route; elsewhere it is a 404 and stays undefined.
  const { data: demo } = useQuery({
    ...demoInfoOptions(),
    retry: false,
    staleTime: 60_000,
    refetchInterval: (query) => (query.state.data?.state === "resetting" ? 5_000 : false),
  });
  const resetting = demo?.state === "resetting";
  const errorCode = AUTH_ERROR_CODES.find((item) => item === error) ?? "google_error";

  if (user) return <Navigate to="/" replace />;

  return (
    <main className="relative grid min-h-svh place-items-center overflow-hidden px-4 py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-64 left-1/2 size-160 -translate-x-1/2 rounded-full bg-primary/8 blur-3xl"
      />

      <div className="relative w-full max-w-sm">
        <div className="flex flex-col items-center text-center">
          <SchoolLogo src={LOGO_URL} schoolName={SCHOOL_NAME} className="size-24 rounded-2xl" />
          <h1 className="font-heading mt-5 text-2xl font-semibold tracking-tight text-balance">
            {SCHOOL_NAME}
          </h1>
        </div>

        <Card className="mt-8">
          <CardContent className="p-6">
            <p className="text-center text-sm leading-6 text-muted-foreground">
              {demo ? t("auth.demoSignInBody") : t("auth.signInBody")}
            </p>
            {demo ? (
              <p className="mt-2 text-center text-xs leading-5 text-muted-foreground">
                {t("auth.demoResetInfo", {
                  time: formatClockTime(demo.next_reset_at, i18n.language),
                })}
              </p>
            ) : null}
            {resetting ? (
              <p
                role="status"
                className="mt-4 rounded-lg border border-warning/40 bg-warning-surface px-3 py-2.5 text-sm text-warning"
              >
                {t("auth.demoResetting")}
              </p>
            ) : null}

            {error ? (
              <p
                role="alert"
                className="mt-4 rounded-lg border border-destructive/30 bg-destructive-surface px-3 py-2.5 text-sm text-destructive"
              >
                {t(`auth.errors.${errorCode}`)}
              </p>
            ) : null}

            <Button
              className="mt-5 w-full"
              size="lg"
              pending={signInPending}
              pendingLabel={t("auth.signingIn")}
              disabled={resetting}
              onClick={() => {
                setSignInPending(true);
                window.location.href = "/api/auth/login";
              }}
            >
              {t("auth.signIn")}
            </Button>

            <p className="mt-4 text-center text-xs leading-5 text-muted-foreground">
              {t("auth.coldStartNotice")}
            </p>
          </CardContent>
        </Card>

        <div className="mt-6 flex justify-center">
          <LanguageSwitch
            language={i18n.language}
            onChange={(language) => void i18n.changeLanguage(language)}
            ariaLabel={t("shell.language")}
          />
        </div>
      </div>
    </main>
  );
}
