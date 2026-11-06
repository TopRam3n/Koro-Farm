# Draft: request for permission to use Ministry agricultural statistics

**For:** the product owner to review, adapt and send. Nothing has been sent.

**To:** Agricultural Marketing Information Division (AMID), Ministry of Agriculture, Fisheries and Mining, Hope
Gardens, Kingston 6. The address on the Ministry's site is psecoffice@moa.gov.jm; ask which office handles data
permissions.

**Status in KoroFarm until answered:** the Ministry source stays `PERMISSION_REQUIRED`. The importer refuses to
apply any Ministry dataset, and no Ministry figure is stored, analysed or modelled.

---

**Subject:** Request for permission to use AMID agricultural statistics in the KoroFarm platform

Dear Sir or Madam,

**Who we are.** [Organisation name] is developing KoroFarm, a supply-coordination platform that helps Jamaican
farmers, exporters and institutional buyers plan, commit and deliver produce. We would like to use the agricultural
statistics published by the Agricultural Marketing Information Division at https://www.moa.gov.jm/content/agricultural-data.
The site states "All Rights Reserved", so we are asking for your written permission and any conditions before we use
them.

**Data we would like to use.**
- All-Island Estimates of Crop Area Reaped (10 years and by quarter).
- All-Island Estimates of Crop Production (10 years and by quarter).
- All-Island Estimates of Farmgate Prices (10 years and by quarter).
- Area Reaped, Production and Farmgate Prices (yearly editions).

**How we would use them.**
1. **Storage and processing.** We would keep the published figures in a secured database. Each figure would carry its
   source, edition and retrieval date. We would never alter them: a revised figure would be stored as a new version
   beside the original.
2. **Analysis.** We would calculate indicators such as yield, trends, seasonality and period-over-period change, to
   help coordinators plan supply and judge risk.
3. **Forecasting.** We would use statistical models trained on the figures to forecast production and prices.
   Forecasts would be labelled as KoroFarm estimates, never as Ministry figures.
4. **Display.** We would show figures and derived analytics to platform users, who are farmers, exporters and buyers.
   Every figure would be attributed: "Source: Agricultural Marketing Information Division, Ministry of Agriculture,
   Fisheries and Mining, Jamaica."
5. **Commercial context.** KoroFarm is [a commercial service / describe the model]. Please tell us whether commercial
   use of the statistics, or of analytics derived from them, needs separate terms.
6. **AI processing (optional; only with your consent).** We may use an AI language model to answer users' questions
   about the published statistics. Any figure in an answer would be checked against your published values before it
   is shown. This would involve sending selected published figures to an external AI service provider. We would not
   do this without your explicit agreement, and we would tell you which provider and what data-retention terms apply.
7. **What we would not do.** We would not imply endorsement by the Ministry, redistribute your publications in bulk,
   or present our estimates as official statistics.

**Questions.**
1. May we store, process, analyse and model these statistics for the uses above? Under what conditions?
2. What attribution wording do you require?
3. Is commercial use, or the commercial use of derived analytics, permitted, and on what terms?
4. May selected published figures be processed by an external AI service, as described in point 6?
5. **Machine-readable data.** Could the datasets be supplied in a machine-readable format, such as CSV or Excel,
   instead of PDF? Are earlier editions and revision notes available, including units, definitions and the dates
   figures became final?
6. Is there a contact for questions about definitions, revisions and new editions?

We would be glad to meet, to share how the data would be shown, and to follow any conditions you set.

Yours faithfully,
[Name, role, organisation, contact details]

---

**After a reply (engineering):**
1. Record the outcome and conditions in `src/backend/data/agriculture/reference/sources.csv` (`licence_review_status`,
   `reuse_conditions`, `attribution_text`) through a reviewed change.
2. Only `APPROVED` lets the importer apply Ministry data.
3. Separately record any consent to AI processing. A decision to send derived forecasts to an external model is a
   per-model-run rights decision (`agri.derived_rights_decisions`), never inferred from this licence.
