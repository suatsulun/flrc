import type { TFunction } from "i18next";

export function academicContextLabels(t: TFunction, locked: string) {
  return {
    year: t("classWorkspace.year"),
    previousYear: t("classWorkspace.previousYear"),
    nextYear: t("classWorkspace.nextYear"),
    semester: t("classWorkspace.semester"),
    semesterShort: (number: number) => t("classWorkspace.semesterShort", { number }),
    active: t("lifecycle.active"),
    setup: t("lifecycle.setup"),
    archived: t("lifecycle.archived"),
    locked,
  };
}

export function appShellLabels(t: TFunction) {
  return {
    menu: t("shell.menu"),
    closeMenu: t("shell.closeMenu"),
    mainNavigation: t("shell.mainNavigation"),
    skipToContent: t("shell.skipToContent"),
    logout: t("logout"),
    collapseSidebar: t("shell.collapseSidebar"),
    expandSidebar: t("shell.expandSidebar"),
    collapseHeader: t("shell.collapseHeader"),
    expandHeader: t("shell.expandHeader"),
    theme: {
      light: t("shell.theme.light"),
      dark: t("shell.theme.dark"),
      system: t("shell.theme.system"),
    },
  };
}
