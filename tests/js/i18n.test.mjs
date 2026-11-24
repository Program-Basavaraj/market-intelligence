// Run: node --test tests/js/i18n.test.mjs   — checks the Kannada translator without a browser.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

function load(lang) {
  const ctx = { window: {}, document: { documentElement: {} }, localStorage: { getItem: () => lang, setItem() {} },
                MutationObserver: class { observe() {} }, NodeFilter: {} };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(new URL("../../site/js/i18n.js", import.meta.url), "utf8"), ctx);
  return ctx.window.I18N;
}

test("exact phrases and patterns translate to Kannada", () => {
  const t = load("kn")._translate;
  assert.equal(t("Price above 50-day SMA"), "ಬೆಲೆ 50-ದಿನದ SMA ಗಿಂತ ಮೇಲಿದೆ");
  assert.equal(t("RSI 55: positive momentum"), "RSI 55: ಧನಾತ್ಮಕ ಆವೇಗ");
  assert.equal(t("Probabilities ↓"), "ಸಂಭವನೀಯತೆಗಳು ↓");
  assert.equal(t(" 120 rows "), " 120 ಸಾಲುಗಳು ");                 // surrounding spaces kept
  assert.match(t("Past 5-day returns of this stock (not a forecast): 10th pct -4.45%, median -0.07%, 90th pct 4.14%; positive 49% of the time."), /ಮುನ್ಸೂಚನೆ ಅಲ್ಲ/);
});

test("numbers and identifiers inside a phrase are preserved", () => {
  const t = load("kn")._translate;
  const out = t(" · ISIN INE000000001 · Information Technology · Mid-cap ");
  assert.match(out, /INE000000001/);
  assert.match(out, /ಮಾಹಿತಿ ತಂತ್ರಜ್ಞಾನ/);
  assert.match(t(" · source: Yahoo Finance · fetched 24 Nov 2026 "), /Yahoo Finance/);
  // Kannada-formatted dates inside an English phrase must not block translation
  assert.match(t(" · source: Yahoo · fetched ನವೆಂ 24, 2026 "), /ಮೂಲ: Yahoo · ಪಡೆದದ್ದು ನವೆಂ 24/);
  assert.match(t("End-of-day close: ₹312.19 (ನವೆಂ 24, 2026)"), /^ದಿನದ ಅಂತ್ಯದ ಮುಕ್ತಾಯ: ₹312.19/);
});

test("already-translated text is never translated again (no information lost)", () => {
  const t = load("kn")._translate;
  const once = t(" · ISIN INE000000001 · Information Technology · Mid-cap ");
  assert.equal(t(once), null);
  assert.equal(t(t(" · source: Yahoo · fetched 24 Nov ")), null);
});

test("bilingual labels keep one side", () => {
  assert.equal(load("kn")._translate("Explain · ವಿವರಣೆ"), "ವಿವರಣೆ");
  assert.equal(load("kn")._translate("Formula · ಸೂತ್ರ"), "ಸೂತ್ರ");
});

test("unknown text (headlines, company names) is left alone", () => {
  const t = load("kn")._translate;
  assert.equal(t("Testcompany B Industries bags order worth Rs 1,200 crore"), null);
  assert.equal(t("RELIANCE"), null);
});

test("language preference and locale", () => {
  assert.equal(load("kn").locale(), "kn-IN");
  assert.equal(load("en").locale(), "en-IN");
  assert.equal(load("en").t("Bullish"), "Bullish");
  assert.equal(load("kn").t("Bullish"), "ಏರುಮುಖ");
});
