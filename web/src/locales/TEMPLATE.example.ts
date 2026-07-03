// Copy this file to <language-code>.ts (e.g. es.ts), translate the values, then register
// it in ./index.ts and in LANGUAGES (../i18n.tsx). Keys are the ENGLISH strings exactly
// as they appear in the components; anything you don't translate falls back to English.
//
// The list below seeds the most visible strings — grep `tr("` for the complete set.

const translations: Record<string, string> = {
  // header + tabs
  "Home": "",
  "Screens": "",
  "Life": "",
  "Climate": "",
  "Settings": "",
  "Connected": "",
  "Offline": "",

  // common actions
  "Save": "",
  "Loading settings…": "",

  // settings
  "Robot connection": "",
  "Robot name": "",
  "Local-only mode": "",
  "Entity wiring — automatic": "",
  "Robot behaviour": "",
  "Head calibration": "",
  "Screensaver & sleep": "",
  "AI & behaviour": "",
};

export default translations;
