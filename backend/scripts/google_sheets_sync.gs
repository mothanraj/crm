/** Google Sheets -> CRM.
 *
 * Column N header must be Employee.
 * A phone number or an email is enough. When either one is valid, the next
 * employee is written into column N. Ticking SEND (column M) posts the row.
 * CRM creates the lead for the employee named in column N.
 *
 * Script properties: WEBHOOK_URL = https://<host>/api/sheets/rows
 *                    WEBHOOK_SECRET = same value as SHEETS_WEBHOOK_SECRET
 * Trigger: onEditHandler, event type On edit.
 * Sheet name must be "Leads".
 */
const CONFIG = {
  SHEET_NAME: 'Leads',
  SEND_COLUMN: 13, // Column M = SEND
  EMPLOYEE_COLUMN: 14 // Column N = Employee
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

    const m = headerMap_(sh);
    if (col === m.cars || col === m.product) {
      if (col === m.cars && String(e.value || '').trim() === '') {
        sh.getRange(row, m.cars).setValue(2);
        return;
      }
      const carsRaw = m.cars > 0 ? sh.getRange(row, m.cars).getValue() : '';
      const productName = m.product > 0 ? sh.getRange(row, m.product).getValue() : '';
      const status = m.syncStatus > 0 ? String(sh.getRange(row, m.syncStatus).getValue() || '') : '';
      const synced = (status.match(/SYNCED:(ENQ-\d+)/) || [])[1] || '';
      const problem = carProblem_(carsRaw, productName);
      if (problem) {
        if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue(synced ? (problem + ' (SYNCED:' + synced + ')') : problem);
        return;
      }
      if (synced) updateProductCars_(sh, row, m, synced);
      return;
    }
    if (col === CONFIG.SEND_COLUMN) {
      if (e.value !== 'TRUE') return;
      const problem = rowProblem_(sh, row, m);
      if (problem) {
        if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue(problem);
        sh.getRange(row, CONFIG.SEND_COLUMN).setValue(false);
        return;
      }
      sendRowToBackend_(sh, row, m);
      return;
    }
    if (col === m.phone || col === m.email) suggestEmployee_(sh, row, m);
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
  const findExact = function(names) {
    for (let i = 0; i < h.length; i++) {
      if (names.indexOf(h[i]) !== -1) return i + 1;
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
    employee: findExact(['employee', 'assigned employee', 'assigned to']),
    syncKey: find(['sync_key', 'sync key']),
    syncStatus: find(['sync_status', 'sync status']),
  };
}

function employeeCol_(m) {
  return m.employee > 0 ? m.employee : CONFIG.EMPLOYEE_COLUMN;
}

function phoneText_(value) {
  if (typeof value === 'number' && isFinite(value)) return String(Math.round(value));
  return String(value || '').trim();
}

function phoneDigits_(value) {
  let d = phoneText_(value).replace(/\D/g, '');
  if (d.indexOf('00') === 0) d = d.substring(2);
  if (d.length === 12 && d.indexOf('91') === 0 && '6789'.indexOf(d.charAt(2)) !== -1) d = d.substring(2);
  else if (d.length === 11 && d.charAt(0) === '0' && '6789'.indexOf(d.charAt(1)) !== -1) d = d.substring(1);
  return d;
}

function emailOk_(value) {
  const s = String(value || '').trim();
  if (!s) return true;
  return /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/.test(s);
}

function rowIsEmpty_(sh, row, m) {
  const cols = ['enq', 'date', 'name', 'company', 'phone', 'email', 'city', 'cars', 'source', 'product', 'requirement', 'quantity', 'remarks', 'priority', 'alt'];
  for (let i = 0; i < cols.length; i++) {
    const col = m[cols[i]];
    if (col > 0 && String(sh.getRange(row, col).getValue() || '').trim() !== '') return false;
  }
  return true;
}

function carProblem_(raw, productName) {
  const text = String(raw || '').trim();
  if (!text) return '';
  const cleaned = text.replace(/,/g, '');
  const match = cleaned.match(/-?\d+(?:\.\d+)?/);
  if (!match || Number(match[0]) !== parseInt(match[0], 10)) return 'NOT SENT - number of cars must be a whole number starting at 2';
  const cars = parseInt(match[0], 10);
  if (cars < 2) return 'NOT SENT - number of cars starts at 2';
  const product = String(productName || '').trim().toLowerCase();
  const oddOk = {
    'puzzle parking': true, 'puzzle parking system': true, 'puzzle': true,
    'pit puzzle parking': true, 'pit puzzle': true,
    'car elevator': true, 'car elevation': true, 'car lift': true, 'car lift parking': true,
    'shuttle parking': true, 'shuttle': true, 'shuttle parking system': true,
    'asrs parking': true, 'asrs': true
  };
  if (cars % 2 === 1 && !oddOk[product]) return 'NOT SENT - even cars only for Two Post, Four Post, Pit Stack, and Tower';
  return '';
}

function rowProblem_(sh, row, m) {
  if (rowIsEmpty_(sh, row, m)) return 'NOT SENT - empty row';
  const phoneValue = m.phone > 0 ? sh.getRange(row, m.phone).getValue() : '';
  const emailValue = m.email > 0 ? sh.getRange(row, m.email).getValue() : '';
  const phoneOk = /^[6-9]\d{9}$/.test(phoneDigits_(phoneValue));
  const emailPresent = String(emailValue || '').trim() !== '';
  const emailValid = emailPresent && emailOk_(emailValue);
  if (String(phoneText_(phoneValue)).trim() !== '' && !phoneOk) return 'NOT SENT - phone must be a 10-digit Indian number';
  if (!phoneOk && !emailValid) {
    if (emailPresent) return 'NOT SENT - invalid email';
    return 'NOT SENT - phone or email is required';
  }
  const carsRaw = m.cars > 0 ? sh.getRange(row, m.cars).getValue() : '';
  const productName = m.product > 0 ? sh.getRange(row, m.product).getValue() : '';
  return carProblem_(carsRaw, productName);
}

function signedPost_(url, payload) {
  const secret = props_().getProperty('WEBHOOK_SECRET');
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = Utilities.computeHmacSha256Signature(timestamp + '.' + payload, secret)
    .map(function(b) { return ('0' + ((b < 0 ? b + 256 : b).toString(16))).slice(-2); })
    .join('');
  return UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: payload,
    muteHttpExceptions: true,
    headers: { 'X-Sheets-Timestamp': timestamp, 'X-Sheets-Signature': signature },
  });
}

function suggestEmployee_(sh, row, m) {
  const problem = rowProblem_(sh, row, m);
  if (problem) {
    if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue(problem);
    return;
  }
  const empCol = employeeCol_(m);
  if (String(sh.getRange(row, empCol).getValue() || '').trim() !== '') return;
  const url = props_().getProperty('WEBHOOK_URL') || '';
  const secret = props_().getProperty('WEBHOOK_SECRET');
  if (!url || !secret) return;
  try {
    const response = signedPost_(url.replace(/\/rows\/?$/, '/next-employee'), '{}');
    if (response.getResponseCode() !== 200) return;
    const data = JSON.parse(response.getContentText() || '{}');
    if (data.employee) sh.getRange(row, empCol).setValue(data.employee);
    else if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('No free employee');
  } catch (err) {
    console.error(err);
  }
}

function updateProductCars_(sh, row, m, enquiryNumber) {
  const url = props_().getProperty('WEBHOOK_URL') || '';
  if (!url) return;
  const get = function(col) {
    if (col <= 0) return '';
    const value = sh.getRange(row, col).getValue();
    return value === null || value === undefined ? '' : value;
  };
  const payload = JSON.stringify({
    enquiry_number: enquiryNumber,
    product: String(get(m.product) || ''),
    cars: String(get(m.cars) || '2'),
  });
  try {
    const response = signedPost_(url.replace(/\/rows\/?$/, '/product-cars'), payload);
    const code = response.getResponseCode();
    if (code === 200) {
      if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('SYNCED:' + enquiryNumber);
      return;
    }
    const text = (response.getContentText() || '').substring(0, 80);
    if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('ERROR HTTP ' + code + ' - ' + text + ' (SYNCED:' + enquiryNumber + ')');
  } catch (err) {
    if (m.syncStatus > 0) sh.getRange(row, m.syncStatus).setValue('ERROR: ' + err.message + ' (SYNCED:' + enquiryNumber + ')');
  }
}

function sendRowToBackend_(sh, row, m) {
  const url = props_().getProperty('WEBHOOK_URL');
  const secret = props_().getProperty('WEBHOOK_SECRET');
  m = m || headerMap_(sh);

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
  const empCol = employeeCol_(m);
  if (m.cars > 0 && String(get(m.cars) || '').trim() === '') sh.getRange(row, m.cars).setValue(2);

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
      cars: String(get(m.cars) || '2'),
      source: get(m.source),
      product: get(m.product),
      requirement: get(m.requirement),
      quantity: get(m.quantity),
      remarks: get(m.remarks),
      priority: get(m.priority),
      alternate_contact: get(m.alt),
      employee: String(get(empCol)).trim(),
    }],
  });

  try {
    const response = signedPost_(url, payload);
    const code = response.getResponseCode();
    const responseText = response.getContentText();
    if (code === 200) {
      let data = {};
      try { data = JSON.parse(responseText || '{}'); } catch (parseError) { data = {}; }
      const enquiryNumber = (data.enquiry_numbers || [])[0] || '';
      const employeeName = (data.employees || [])[0] || '';
      if (employeeName) sh.getRange(row, empCol).setValue(employeeName);
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
