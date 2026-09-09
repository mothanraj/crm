# Excel Analysis — MARKETING LEADS FUNNEL TRACKER (5) (1).xlsx

> Source file: `MARKETING LEADS FUNNEL TRACKER (5) (1).xlsx` (593 KB). Read-only analysis via stdlib ZIP/XML parsing. Original file MUST NOT be modified. PostgreSQL becomes source of truth after migration.

## 1. Workbook overview

| # | Sheet name | File | Rows (physical) | Role |
|---|-----------|------|-----------------|------|
| 1 | 📊 Dashboard (1) | sheet1 | ~30 | Live funnel dashboard (COUNTA/COUNTIF/COUNTIFS). 23 merges, 0 validations, ~13 chart drawings |
| 2 | 📋 Leads Tracker (1) | sheet2 | 3000 alloc / **629 data rows** | **Master lead table**, structured as `Table1 A1:AE3000` |
| 3 | Sheet16 | sheet3 | ~18 | A+ pipeline scratch (manual) |
| 4 | A+ Enquiry Report | sheet4 | 1000 alloc | Manual A+ watchlist |
| 5 | Quotation Summary | sheet5 | 1000 alloc / ~30 quote rows | Quotation register, links to tracker via Enquiry No |
| 6 | Details Report | sheet6 | ~30 | Parameterised source-wise report (reads Helper) |
| 7 | Sheet17 | sheet7 | 10 | Meta staging sample |
| 8 | Rajesh - E Star New WithOUT OTP | sheet8 | 293 | Meta Lead Ads export (Jun 12 → Aug) |
| 9 | Investor & CHPP | sheet9 | 14 | Filtered tracker view (Channel Partner / Investor only) |
| 10 | meta leads | sheet10 | 293 | Duplicate of sheet 8 |
| 11 | Waremat Expo - leads | sheet11 | 52 | Expo visitor log (Jul 30/31) |
| 12 | expesnes [sic] | sheet12 | 70 | Expense log + pasted meta rows. **DO NOT MIGRATE** |
| 13 | Helper (do not edit) | sheet13 | ~592 | Formula engine: `A='Tracker'!A`, `B=parsed date`, `C=N`, `D=Q`, `F='Quotation Summary'!E`, `G/H/I=INDEX/MATCH`, `J=IF(P<>\"\",P,L)`, `K=units` |

## 2. Leads Tracker columns (A–AE, 31 cols)

| Col | Header | Filled /629 | Type | Notes |
|-----|--------|-------------|------|-------|
| A | Enq no | 629 | numeric 1..~629 | **dupes: 76×2, 449×2, 473×2 → 626 distinct**. Preserve as `legacy_enquiry_no` |
| B | Date Received | 629 | mixed: Excel serials (46158…) + text (`1.9.2026`, `13.08.2026`, `26th june`, `10.6.26`) | Needs serial+text parser; range May–Sep 2026 |
| C | Lead Name / Full Name | 626 | text | 3 blanks |
| D | Company / Organisation | 447 | text | 182 blanks |
| E | Contact No. | 610 | mixed: sci-notation `9.92E9`, `p:+91…`, `+971…` | 599 distinct, 8+ dupe pairs. Normalise to digits for dedup |
| F | City | 577 | text | Free text, varying case |
| G | No. of Cars | 412 | mixed text/num, 132 distinct | `20, 100, 50` top; junk `50 cars`, `ten to twenty`, `11+11`. Keep `quantity_raw` + parsed `quantity_num` |
| H | Client Inputs/information | 77 | text | → activity |
| I | Client / Lead Note | 371 | text | → activity |
| J | Followup Note / Remarks-1 | 516 | text | → activity timeline |
| K | Followup by NSM | 30 | text | → activity (author NSM) |
| L | Followup Note / Remarks-2 | 67 | text | → activity |
| M | Followup Note / Remarks-2 2 | 19 | text | → activity |
| N | Staus [sic] | 627 | dropdown | See §3. 2 blanks |
| O | Qutation [sic] Sent | 6 | `sent/Sent/send` | → quotation.sent flag |
| P | Project Value | 5 | `3.9 to 4.8 lakhs`, `3600000`, `9,00,000\n73,50,0000` | → quotation amount (parse best-effort) |
| Q | Lead Source | 625 | dropdown | See §4 |
| R | Last Contacted | 59 | free dates (`26th june`, `10.6.26`, `Ram`) | → activity, parse best-effort |
| S | Priority / Stage | 29 | `A 18, B 6, A Plus 4, backtick 1` | → `priority` |
| T | Product / Type | 207 | 32 distinct, 422 blank | See §5 — heavy normalisation needed |
| U | Primary Owner | 324 | dropdown | 305 unassigned. See §6 |
| V | TAT Time | 0 | empty | Greenfield (SLA handled by CRM) |
| W | Assigned To (Technical) | 44 | dropdown | See §6 |
| X | Secondary Support Person | 11 | free text | Incl. typo `Sundarm`. See §6 |
| Y | Source Documents | 0 | empty | Greenfield (documents module) |
| Z | Product / Svc Interested In | 0 | empty | Drop |
| AA | Converted Date | 0 | empty | Greenfield |
| AB | Reason Lost | 2 | `Budget Issues`, long text | → status_history reason / lost_reason |
| AC | TAT (Days) | 0 | empty | Greenfield |
| AD | Email ID | 80 | email-ish | Validate on import |
| AE | Remarks / Additional Notes | 14 | text | → activity |

Only 7 stray cell formulas in tracker (cols E/C/O) — no business logic. All logic lives in Dashboard/Details/Helper.

## 3. Status dropdowns vs actual

Validations:
- `N2:N349,N351:N793`: `In Followup, A - Prospect, RNR / Not reachable, Not Interested/Spam, A+ - Immediate, Converted, Duplicate, New Lead, Investor, Channel Partner, Approval Client`
- **Anomaly `N350` single cell**: `In Followup, A - Prospect, RNR / Not reachable, Not Interested, A+ - Immediate, Converted, Duplicate, New Lead, Reference` (no `/Spam`, no Investor/Channel/Approval, adds `Reference`)

Actual usage (627 filled, 12 distinct): In Followup 391, RNR 86, A-Prospect 49, Not Interested 42, New Lead 14, Channel Partner 13, A+ 9, Investor 9, Converted 5, Not Interested/Spam 4, Duplicate 4, Approval Client 1. `Reference` never used.

**Bugs**: Dashboard `Not Interested=COUNTIF("Not Interested")=42` misses 4 `/Spam` rows (true 46). `Other/Unmapped = Total − mapped = 33` absorbs Channel Partner 13 + Investor 9 + Duplicate 4 + Spam 4 + Approval 1 + blanks 2.

**Canonical statuses (11)**: New Lead, In Followup, A - Prospect, A+ - Immediate, RNR / Not reachable, Not Interested (merge +/Spam), Converted, Duplicate, Investor, Channel Partner, Approval Client. (Add `Reference` only if business confirms.)

## 4. Lead sources

DV `Q2:Q3000`: Facebook/Instagram, Google Ads, India Mart, Direct Call, Referral, WhatsApp, Email Campaign, Email Enquiry, SEO, Others, Expo/Stall.

Actual (625 filled, 10 distinct): FB/IG 386, Direct Call 91, India Mart 85, SEO 22, Google Ads 16, Referral 11, Email Enquiry 5, Others 5, Email Campaign 2, Expo/Stall 2. **WhatsApp 0 rows** (keep as master, 0 is valid). 4 blanks → `Others` or import error.

Quotation sheet uses dirty variants: `META, IM, DIRECT CALL, REFFERAL [sic]` → map to canonical on import.

## 5. Products — the messiest column

`T` actual 32 distinct (207 filled): Tower Parking System 33, tower_parking_system 26, Shuttle 28, shuttle/robotic 22, Two Post Stack Parking 17, two_post 14, Two Post stack 10, puzzle variants (Puzzle Parking System 14, puzzle parking system 7, puzzle_parking_system 4, …), STACK PARKING 7, Tower parking System 3, Two Post Stack Parking System 2, Pit Puzzle 2, junk singletons: `detaoils shared in whatsapp`, `Will be decide after 2nd round of discussion.`, `BUS PARKING`, `stack paring`, `tower parking`, ` `` `, backtick.

**Canonical products (6)** + `product_aliases` for all 32 raw strings:
1. Two Post Stack Parking (aliases: all case/snake variants + `1+1`, `Two Level Stack`, `Stack`, `STACK PARKING`, `stack parking/par­ing`)
2. Puzzle Parking System (aliases: all puzzle case variants + `Puzzle`)
3. Tower Parking System (aliases: all tower case/snake variants + `Tower`, `108 nos Tower parking`)
4. Shuttle / Robotic Parking (aliases: `Shuttle`, `Robotic Shuttle`, `shuttle/robotic_parking_`, `Robotic / Shuttle Parking`, `PUZZLE OR SHUTTLE` → needs review)
5. Pit / Fixed Stack Parking (aliases: `Pit Stack`, `Pit Puzzle Parking`, `Three Level Stack`, `CAR LIFT`, `SS Car Parking`)
6. MLCP / ASRS / Custom (Expo `MLCP/ASRS`, `CAR STACK`, `BUS PARKING` → triage; junk strings → import warning, not products)

Quotation `H Parking Type` is cleaner — reuse its names as canonical hints.

## 6. Employees

DV ranges `U2:U574,W2:W617,…` list 7 names (no Senthilkumaran); **only `U575`** lists 8 with Senthilkumaran. Actual `U`: Kanchana 208, Sundaram 44, Karthik 28, Archith 18, Rajesh 17, Ajith 5, Ram 2, `Ram kumar 1`, Senthilkumaran 1. `W`: Ram 25, Archith 8, Sundaram 5, Ajith 4, Karthik 1, Kanchana 1. `X` free text: Archith 8, Karthik 1, Sundaram 1, `Sundarm 1 [sic]`.

**Historical Excel owners (analysis only — not seeded in the app)**: Kanchana, Karthik, Rajesh, Archith, Sundaram, Ram (merge `Ram kumar`), Ajith, Senthilkumaran. `Sundarm→Sundaram` alias on import name matching. Live employees are created by admin after install.

## 7. Dashboard formulas (must be replaced by PG queries)

- KPIs: `COUNTA(A)`, `COUNTIF(N, status)` per card; `Other = Total − 8 mapped`.
- Leads-by-Source: `COUNTIF(Q, source)` + `COUNTIFS(Q+N)` × 6 statuses + `Conv% = Converted/Total`. `Others` row = residual (`B7−SUM(C14:C22)` etc.) — **recompute explicitly in PG, never residual**.
- Monthly: `COUNTIFS(Helper.B, month)` + quote/converted counts from Helper H/B.
- Details Report: `COUNTIFS/SUMIFS` on Helper with Effective From/To (`IF(C4="Month-wise",…)`).
- 13 chart drawings reference these ranges.

## 8. Data-quality issues

Enq dupes (76/449/473); phone sci-notation + prefixes + intl (`+971`); date salad (serials + 6+ text formats); 305 unassigned owners; 422 blank products; free-text R/G/P/O/S; `Sundarm`, `Ram kumar`, `REFFERAL`, `Qutation/Staus/expesnes` typos; 4 blank sources; 2 blank statuses; 3 blank names; backtick/junk cells; Investor&CHPP col K header literally `an`; meta `O` column mixes counts/emails/text (`sridharj2010@gmail.com` in cars field); `meta leads` dup of `Rajesh…` sheet; expenses mixed into `expesnes` rows 28+.

## 9. CRM mapping

Tracker A→`legacy_enquiry_no` (+ new `ENQ-%06d`); B→`enquiry_date`; C/D/E/AD/F→contact fields; G→`quantity_raw`+`quantity_num`; H/I/J/K/L/M/AE→`lead_activities`; N→`status_id` (+ history seed row); O/P→`quotations`; Q→`source_id`; R→activity; S→`priority`; T→`product_id` via aliases; U/W/X→`primary/technical/secondary_user_id`; AB→`lost_reason`; Quotation Summary→`quotations` (ref unique, revisions, amounts, `lead_id` via Enquiry No); Meta sheets→intake staging (phone dedup); Expo→leads (`Expo/Stall`); Investor&CHPP/A+/Sheet16 = views/reports.

## 10. Do NOT migrate

`expesnes` sheet; Dashboard/Details/Helper computed values; merges/charts/styles; empty V/AC/Y/Z/AA; junk product strings as products; `Reference` status (unless confirmed); duplicate `meta leads` sheet (dedupe by Meta `id`).

## 11. Normalisation checklist

Products (32→6 + aliases); statuses (merge Spam, confirm Reference/Approval Client); sources (MAP META→Facebook/Instagram, IM→India Mart, REFFERAL→Referral, DIRECT CALL→Direct Call); employees (Ram kumar→Ram, Sundarm→Sundaram); phones (strip to digits, keep raw); dates (serial + multi-format parser); quantities (parse num, keep raw); quotation refs (unique, revisions as rows); Meta ids (unique staging key).
