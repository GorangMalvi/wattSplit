export function formatMoney(value) {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  const amount = Math.abs(Number(value)).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  // Round first so -0.001 doesn't show as "−₹0.00".
  return Math.round(Number(value) * 100) < 0 ? `−₹${amount}` : `₹${amount}`;
}

export function formatNumber(value, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}

// "2026-03" -> "Mar 26"
export function formatMonth(month) {
  const [year, mon] = month.split('-').map(Number);
  return new Date(year, mon - 1, 1).toLocaleString(undefined, { month: 'short', year: '2-digit' });
}

// What the prepaid meter deducted: opening + recharge - closing, or null
// until all three are known (same rule as db.meter_bill on the backend).
export function meterBill(opening, recharge, closing) {
  const [o, r, c] = [opening, recharge, closing].map((v) =>
    v === '' || v === null || v === undefined ? NaN : Number(v)
  );
  if ([o, r, c].some(Number.isNaN)) return null;
  return Math.round((o + r - c) * 100) / 100;
}

export const today = () => {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
