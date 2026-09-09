import type { ReactNode } from "react";
import { PageHeader } from "@flrc/ui/components/page-header";

type AdminPageProps = {
  title: string;
  description?: string;
  actions?: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
};

/**
 * Standard top of an admin screen.
 *
 * Renders a fragment on purpose: the header and the page's sections become
 * direct children of the shell's `<main>`, so its `space-y` rhythm applies to
 * every block without each page repeating spacing classes.
 */
export function AdminPage({ title, description, actions, meta, children }: AdminPageProps) {
  return (
    <>
      <PageHeader title={title} description={description} actions={actions} meta={meta} />
      {children}
    </>
  );
}
