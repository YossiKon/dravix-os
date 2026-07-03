// Extra-language dictionaries, keyed by language code. Hebrew + English live inline in
// the components (see ../i18n.tsx); every OTHER language maps the ENGLISH text → its
// translation here. Missing keys simply fall back to English — a partial translation
// is fine and ships.
//
// To add a language:
//   1. copy TEMPLATE.example.ts → <code>.ts and translate what you can
//   2. import it here and add it to EXTRA_LOCALES
//   3. register the language in LANGUAGES (../i18n.tsx)
//
// import es from "./es";

export const EXTRA_LOCALES: Record<string, Record<string, string>> = {
  // es,
};
