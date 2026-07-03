// Tiny i18n: a language context (he/en) + an inline `tr("עברית","English")` helper.
// No dictionary files to maintain — each string carries both languages at its use site.
// Switching language also flips the document direction (RTL ⇄ LTR) and persists the choice.
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

export type Lang = "he" | "en";

interface LangState {
  lang: Lang;
  setLang: (l: Lang) => void;
}

const STORAGE_KEY = "dravix_lang";
const LangContext = createContext<LangState>({ lang: "he", setLang: () => undefined });

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "he" || saved === "en") return saved;
    // First visit: Hebrew browsers get Hebrew, everyone else gets English.
    const nav = typeof navigator !== "undefined" ? navigator.language : "";
    if (nav && !nav.toLowerCase().startsWith("he")) return "en";
  } catch {
    /* localStorage may be unavailable */
  }
  return "he";
}

export function LangProvider(props: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(initialLang);
  useEffect(() => {
    const el = document.documentElement;
    el.lang = lang;
    el.dir = lang === "he" ? "rtl" : "ltr";
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      /* ignore */
    }
  }, [lang]);
  return <LangContext.Provider value={{ lang, setLang }}>{props.children}</LangContext.Provider>;
}

export function useLang(): LangState {
  return useContext(LangContext);
}

// One hook for everything: the active language + a translate helper.
//   const { tr, lang } = useI18n();   →   tr("עברית", "English")
export function useI18n() {
  const { lang, setLang } = useContext(LangContext);
  return {
    lang,
    setLang,
    tr: (he: string, en: string) => (lang === "en" ? en : he),
  };
}
