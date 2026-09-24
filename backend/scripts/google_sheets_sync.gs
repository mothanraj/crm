/** Google Sheets -> CRM. Sends one row only when column M (SEND) is ticked.
 *
 * Script properties: WEBHOOK_URL = https://<host>/api/sheets/rows
 *                    WEBHOOK_SECRET = same value as SHEETS_WEBHOOK_SECRET
 * Trigger: onEditHandler, event type On edit.
 * Sheet name must be "Leads". Only Contact No. is required.
 * A blank row is not sent. An enquiry number, when present, is stored as ENQ-000001.
 */
const CONFIG = {
  SHEET_NAME: 'Leads',
  SEND_COLUMN: 13 // Column M = SEND
};

function props_() {
  return PropertiesService.getScriptProperties();
}

function onEditHandler(e) {
  try {
    const sh = e.range.getSheet();
    const row = e.range.getRow();
    const col = e.range.getColumn();

    if (sh.getName() !== CONFIG.SHEET_NAME) return;
    if (row === 1) return;
    if (col !== CONFIG.SEND_COLUMN) return;
    if (e.value !== 'TRUE') return;

    const m = headerMap_(sh);
    if (rowIsEmpty_(sh, row, m)) {
      if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('NOT SENT - empty row');
      return;
    }
    const phoneValue = m.phone > 0 ? sh.getRange(row, m.phone).getValue() : '';
    if (String(phoneValue).trim() === '') {
      if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('NOT SENT - Contact No. is required');
      return;
    }
    sendRowToBackend_(sh, row);
  } catch (err) {
    console.error(err);
  }
}

function headerMap_(sh) {
  const h = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0]
    .map(function(x) { return String(x || '').trim().toLowerCase(); });
  const find = function(kws) {
    for (let i = 0; i < h.length; i++) {
      for (const k of kws) {
        if (h[i] && h[i].indexOf(k) !== -1) return i + 1;
      }
    }
    return -1;
  };
  return {
    enq: find(['enq', 'enquiry no', 'enquiry number']),
    date: find(['date received', 'received date', 'date']),
    name: find(['lead name', 'full name', 'customer name', 'name']),
    company: find(['company', 'organisation', 'organization']),
    phone: find(['contact no', 'contact number', 'phone', 'mobile']),
    email: find(['email']),
    city: find(['city']),
    cars: find(['no. of cars', 'no of cars', 'cars']),
    source: find(['lead source', 'source']),
    product: find(['product', 'type']),
    requirement: find(['requirement']),
    quantity: find(['quantity']),
    remarks: find(['remarks', 'remark']),
    priority: find(['priority']),
    alt: find(['alternate', 'alt contact']),
    syncKey: find(['sync_key', 'sync key']),
    syncStatus: find(['sync_status', 'sync status']),
  };
}

function phoneText_(value) {
  if (typeof value === 'number' && isFinite(value)) return String(Math.round(value));
  return String(value || '').trim();
}

function rowIsEmpty_(sh, row, m) {
  const cols = ['enq', 'date', 'name', 'company', 'phone', 'email', 'city', 'cars', 'source', 'product', 'requirement', 'quantity', 'remarks', 'priority', 'alt'];
  for (let i = 0; i < cols.length; i++) {
    const col = m[cols[i]];
    if (col > 0 && String(sh.getRange(row, col).getValue() || '').trim() !== '') return false;
  }
  return true;
}

function sendRowToBackend_(sh, row) {
  const url = props_().getProperty('WEBHOOK_URL');
  const secret = props_().getProperty('WEBHOOK_SECRET');
  const m = headerMap_(sh);

  const phoneValue = m.phone > 0 ? sh.getRange(row, m.phone).getValue() : '';
  if (rowIsEmpty_(sh, row, m)) {
    if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('NOT SENT - empty row');
    return;
  }
  if (String(phoneValue).trim() === '') {
    if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('NOT SENT - Contact No. is required');
    return;
  }
  if (!url || !secret) {
    if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('ERROR: WEBHOOK CONFIG');
    return;
  }

  let key = '';
  if (m.syncKey > 0) key = String(sh.getRange(row, m.syncKey).getValue() || '').trim();
  if (!key) {
    key = Utilities.getUuid();
    if (m.syncKey > 0) sh.getRange(row, m.syncKey).setValue(key);
  }

  const get = function(col) {
    if (col <= 0) return '';
    const value = sh.getRange(row, col).getValue();
    if (value === null || value === undefined) return '';
    return value;
  };

  if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('SENDING...');

  const payload = JSON.stringify({
    sheet_id: CONFIG.SHEET_NAME,
    rows: [{
      row_id: row,
      external_key: key,
      enq: get(m.enq),
      date: get(m.date),
      name: get(m.name),
      company: get(m.company),
      phone: String(phoneText_(get(m.phone))),
      email: get(m.email),
      city: get(m.city),
      cars: String(get(m.cars)),
      source: get(m.source),
      product: get(m.product),
      requirement: get(m.requirement),
      quantity: get(m.quantity),
      remarks: get(m.remarks),
      priority: get(m.priority),
      alternate_contact: get(m.alt),
    }],
  });

  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = Utilities.computeHmacSha256Signature(timestamp + '.' + payload, secret)
    .map(function(b) { return ('0' + ((b < 0 ? b + 256 : b).toString(16))).slice(-2); })
    .join('');

  try {
    const response = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: payload,
      muteHttpExceptions: true,
      headers: { 'X-Sheets-Timestamp': timestamp, 'X-Sheets-Signature': signature },
    });
    const code = response.getResponseCode();
    const responseText = response.getContentText();
    if (code === 200) {
      let data = {};
      try { data = JSON.parse(responseText || '{}'); } catch (parseError) { data = {}; }
      const enquiryNumber = (data.enquiry_numbers || [])[0] || '';
      if (m.syncStatus > 0) {
        sh.getRange(row, m.syncStatus).setValue(enquiryNumber ? ('SYNCED:' + enquiryNumber) : 'SYNCED');
      }
      sh.getRange(row, CONFIG.SEND_COLUMN).setValue(false);
      return;
    }
    let errorMessage = responseText || '';
    if (errorMessage.length > 100) errorMessage = errorMessage.substring(0, 100);
    if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('ERROR HTTP ' + code + ' - ' + errorMessage);
    console.error('Backend error: ' + code + ' ' + responseText);
  } catch (err) {
    if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('ERROR: ' + err.message);
    console.error(err);
  }
}
