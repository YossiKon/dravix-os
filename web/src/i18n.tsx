// Tiny i18n, built to grow.
//
// HOW STRINGS WORK: every string carries Hebrew + English inline at its use site —
// `tr("עברית", "English")`. English doubles as the KEY for every other language.
//
// ── ADDING A LANGUAGE (2 small steps, no other code changes) ─────────────────────
//  1. Create `src/locales/<code>.ts` that default-exports a Record<string, string>
//     mapping the ENGLISH text → your translation (missing keys fall back to English).
//     A ready-to-copy template lives in `src/locales/TEMPLATE.example.ts`.
//  2. Register it below: add one line to LANGUAGES and one to EXTRA_LOCALES.
// The header button cycles through every registered language automatically, and the
// document direction follows the language's `dir`.
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { EXTRA_LOCALES } from "./locales";

export const LANGUAGES = [
  { code: "en", label: "English", short: "EN", dir: "ltr" },
  { code: "he", label: "עברית", short: "עב", dir: "rtl" },
  // { code: "es", label: "Español", short: "ES", dir: "ltr" },   ← example: step 2
] as const;

export type Lang = (typeof LANGUAGES)[number]["code"];

const CODES = LANGUAGES.map((l) => l.code) as readonly string[];
const STORAGE_KEY = "dravix_lang";

export function langMeta(code: Lang) {
  return LANGUAGES.find((l) => l.code === code) ?? LANGUAGES[0];
}

// The one translation rule, usable outside React too (pure function):
// Hebrew is authored inline; English is authored inline AND is the lookup key
// for every additional language.
export function biPick(lang: Lang, he: string, en: string): string {
  if (lang === "he") return he;
  if (lang === "en") return en;
  return EXTRA_LOCALES[lang]?.[en] ?? en;
}

interface LangState {
  lang: Lang;
  setLang: (l: Lang) => void;
}

const LangContext = createContext<LangState>({ lang: "en", setLang: () => undefined });

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && CODES.includes(saved)) return saved as Lang;
    // First visit: match the browser language when we have it; ENGLISH otherwise.
    const nav = (typeof navigator !== "undefined" ? navigator.language : "").toLowerCase();
    const hit = LANGUAGES.find((l) => nav.startsWith(l.code));
    if (hit) return hit.code;
  } catch {
    /* localStorage may be unavailable */
  }
  return "en";
}

export function LangProvider(props: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(initialLang);
  useEffect(() => {
    const el = document.documentElement;
    el.lang = lang;
    el.dir = langMeta(lang).dir;
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
    tr: (he: string, en: string) => biPick(lang, he, en),
    // The next language in the registry — for the header's cycle button.
    nextLang: LANGUAGES[(LANGUAGES.findIndex((l) => l.code === lang) + 1) % LANGUAGES.length],
  };
}
