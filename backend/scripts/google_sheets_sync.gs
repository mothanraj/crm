/** Google Sheets -> CRM backend push sync (bound script).
 *
 * Setup (once):
 *  1. Sheet headers must match tracker names (Enq no, Date Received,
 *     Lead Name, Company, Contact No., Email ID, City, No. of Cars,
 *     Lead Source, Product / Type, Requirement, Quantity, Remarks,
 *     Priority, Alternate Contact). Order-free.
 *  2. Add two trailing columns: SYNC_KEY, SYNC_STATUS (headers exact).
 *  3. Extensions > Apps Script > paste this file > set CONFIG below >
 *     Triggers > Add: onEditHandler (on edit), flushDirty (every 1 min).
 *  4. Script Properties: WEBHOOK_URL=https://<backend>/api/sheets/rows,
 *     WEBHOOK_SECRET=<same as backend SHEETS_WEBHOOK_SECRET>.
 *
 * Flow: edit marks row dirty (SYNC_STATUS=PENDING) -> 1-min flush batches
 * dirty rows -> POST {sheet_id, rows} with HMAC headers -> backend
 * validates (same rules as Excel upload) -> inserts valid, queues
 * duplicates/invalid for admin review in ImportPage -> writes status back.
 * Website updates live via SSE/polling, no manual refresh.
 */
const CONFIG = {
  SHEET_NAME: 'Leads Tracker (1)',
  BATCH_SIZE: 50,
};

function props_() {
  return PropertiesService.getScriptProperties();
}

function onEditHandler(e) {
  try {
    const sh = e.range.getSheet();
    if (sh.getName() !== CONFIG.SHEET_NAME) return;
    if (e.range.getRow() === 1) return;
    markDirty_(sh, e.range.getRow());
  } catch (err) { console.error(err); }
}

function headerMap_(sh) {
  const h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
    .map(x => String(x || '').trim().toLowerCase());
  const find = (kws) => {
    for (let i = 0; i < h.length; i++)
      for (const k of kws) if (h[i] && h[i].indexOf(k) !== -1) return i + 1;
    return -1;
  };
  return {
    enq: find(['enq']), date: find(['date received', 'received date', 'date']),
    name: find(['lead name', 'full name', 'customer name', 'name']),
    company: find(['company', 'organisation', 'organization']),
    phone: find(['contact no', 'contact number', 'phone', 'mobile']),
    email: find(['email']), city: find(['city']),
    cars: find(['no. of cars', 'no of cars', 'cars']),
    source: find(['lead source', 'source']), product: find(['product', 'type']),
    requirement: find(['requirement']), quantity: find(['quantity']),
    remarks: find(['remarks', 'remark']), priority: find(['priority']),
    alt: find(['alternate', 'alt contact']),
    syncKey: find(['sync_key', 'sync key']), syncStatus: find(['sync_status', 'sync status']),
  };
}

function markDirty_(sh, row) {
  const m = headerMap_(sh);
  if (m.syncStatus < 0) return;
  const cur = sh.getRange(row, m.syncStatus).getValue();
  if (String(cur).indexOf('SYNCED') === 0) return; // already synced edits need re-push: set PENDING manually
  sh.getRange(row, m.syncStatus).setValue('PENDING');
}

function flushDirty() {
  const url = props_().getProperty('WEBHOOK_URL');
  const secret = props_().getProperty('WEBHOOK_SECRET');
  if (!url || !secret) { console.error('WEBHOOK_URL/SECRET missing'); return; }
  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheetByName(CONFIG.SHEET_NAME);
  if (!sh) return;
  const m = headerMap_(sh);
  if (m.syncStatus < 0 || m.name < 0 || m.phone < 0) {
    console.error('Missing required columns (name/phone/SYNC_STATUS)');
    return;
  }
  const last = sh.getLastRow();
  const vals = sh.getRange(2, 1, Math.max(0, last - 1), sh.getLastColumn()).getValues();
  const cell = (r, c) => (c > 0 ? vals[r][c - 1] : '');
  const batch = [];
  const rowNos = [];
  for (let r = 0; r < vals.length; r++) {
    const st = String(cell(r, m.syncStatus) || '');
    const hasData = String(cell(r, m.name) || '') || String(cell(r, m.phone) || '');
    if (!hasData || st.indexOf('SYNCED') === 0) continue;
    if (batch.length >= CONFIG.BATCH_SIZE) break;
    let key = String(cell(r, m.syncKey) || '').trim();
    if (!key) {
      key = Utilities.getUuid();
      sh.getRange(r + 2, m.syncKey).setValue(key);
    }
    batch.push({
      row_id: r + 2, external_key: key,
      enq: cell(r, m.enq), date: cell(r, m.date), name: cell(r, m.name),
      company: cell(r, m.company), phone: String(cell(r, m.phone)),
      email: cell(r, m.email), city: cell(r, m.city), cars: String(cell(r, m.cars)),
      source: cell(r, m.source), product: cell(r, m.product),
      requirement: cell(r, m.requirement), quantity: cell(r, m.quantity),
      remarks: cell(r, m.remarks), priority: cell(r, m.priority),
      alternate_contact: cell(r, m.alt),
    });
    rowNos.push(r + 2);
  }
  if (!batch.length) return;
  const payload = JSON.stringify({ sheet_id: CONFIG.SHEET_NAME, rows: batch });
  const ts = String(Math.floor(Date.now() / 1000));
  const sig = Utilities.computeHmacSha256Signature(ts + '.' + payload, secret)
    .map(b => ('0' + ((b < 0 ? b + 256 : b).toString(16))).slice(-2)).join('');
  const resp = UrlFetchApp.fetch(url, {
    method: 'post', contentType: 'application/json', payload: payload, muteHttpExceptions: true,
    headers: { 'X-Sheets-Timestamp': ts, 'X-Sheets-Signature': sig },
  });
  const code = resp.getResponseCode();
  let data = {};
  try { data = JSON.parse(resp.getContentText() || '{}'); } catch (e) { data = {}; }
  if (code === 200) {
    const byRow = {};
    (data.errors || []).forEach(e => { byRow[String(e.row)] = e; });
    batch.forEach((b, i) => {
      const err = byRow[String(b.row_id)];
      sh.getRange(rowNos[i], m.syncStatus)
        .setValue(err ? ((err.reason || 'ERROR') + ':' + (err.error || '')) : ('SYNCED:' + ((data.enquiry_numbers || [])[0] || '')));
    });
  } else {
    console.error('sync failed ' + code + ' ' + resp.getContentText().slice(0, 300));
  }
}
