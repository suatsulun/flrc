import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import fr from "./locales/fr.json";
import de from "./locales/de.json";
import tr from "./locales/tr.json";

export const initI18n = () => {
  i18n
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
      resources: {
        en: { common: en },
        fr: { common: fr },
        de: { common: de },
        tr: { common: tr },
      },
      defaultNS: "common",
      fallbackLng: "tr",
      // A browser set to en-GB or de-AT must resolve to en / de, not just for
      // the UI strings but because `i18n.language` is sent to the API as the
      // `locale` for column labels. An unrecognised code there silently falls
      // back to Turkish labels.
      supportedLngs: ["tr", "en", "de", "fr"],
      nonExplicitSupportedLngs: true,
      load: "languageOnly",
      interpolation: {
        escapeValue: false,
      },
    });
};

export { default as i18n } from "i18next";

export { academicContextLabels, appShellLabels } from "./labels";
