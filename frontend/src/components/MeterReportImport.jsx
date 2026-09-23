import { useState } from 'react';
import { uploadMeterReport } from '../api';
import { formatMoney, formatMonth, formatNumber } from '../format';
import ErrorAlert from './ErrorAlert';

// Owner: upload the meter provider's Monthly Consumption Report, preview the
// months it contains, then import them (main meter readings + amount deducted).
function MeterReportImport({ onImported, onCancel }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const choose = async (e) => {
    const picked = e.target.files?.[0];
    setFile(picked || null);
    setPreview(null);
    setError(null);
    if (!picked) return;
    setBusy(true);
    try {
      setPreview(await uploadMeterReport(picked, { dryRun: true }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const importNow = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await uploadMeterReport(file, { dryRun: false });
      onImported(result.months);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const months = preview?.months || [];
  const updates = months.filter((m) => m.exists).length;

  return (
    <div className="card space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Import meter report</h2>
        <p className="mt-1 text-sm text-slate-500">
          Upload the prepaid meter's <span className="font-medium">Monthly Consumption Report</span>{' '}
          (.xlsx). For each month it fills in the main meter readings and the bill:{' '}
          <span className="font-medium">opening balance + recharge − closing balance</span>, i.e.
          everything the meter deducted (energy, duty, fixed charges, VCAP, rebates). The rate per
          unit is that amount ÷ units. Sub-meter readings stay as they are.
        </p>
      </div>

      <input
        type="file"
        accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        onChange={choose}
        disabled={busy}
        className="block w-full text-sm"
        aria-label="Meter report file"
      />

      {error && <ErrorAlert message={error} />}
      {busy && !preview && <p className="text-sm text-slate-500">Reading the report…</p>}

      {preview && (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Month</th>
                  <th className="text-right">Main meter</th>
                  <th className="text-right">Units</th>
                  <th className="text-right">Opening bal.</th>
                  <th className="text-right">Recharge</th>
                  <th className="text-right">Closing bal.</th>
                  <th className="text-right">Deducted (bill)</th>
                  <th className="text-right">Rate / unit</th>
                  <th>In app</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {months.map((m) => (
                  <tr key={m.month}>
                    <td className="font-medium">{formatMonth(m.month)}</td>
                    <td className="text-right tabular-nums">
                      {formatNumber(m.main_start_reading)} → {formatNumber(m.main_end_reading)}
                    </td>
                    <td className="text-right tabular-nums">{formatNumber(m.units)}</td>
                    <td className="text-right tabular-nums">{formatMoney(m.meter_opening_balance)}</td>
                    <td className="text-right tabular-nums">{formatMoney(m.meter_recharge)}</td>
                    <td className="text-right tabular-nums">{formatMoney(m.meter_closing_balance)}</td>
                    <td className="text-right font-medium tabular-nums">{formatMoney(m.monthly_bill)}</td>
                    <td className="text-right tabular-nums">{formatMoney(m.rate_per_unit)}</td>
                    <td className="text-xs text-slate-500">
                      {m.exists ? `Update (bill was ${formatMoney(m.current_bill)})` : 'New month'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-sm text-slate-500">
            {months.length} month{months.length === 1 ? '' : 's'}: {months.length - updates} new,{' '}
            {updates} updated. DG bills and notes you entered are kept.
          </p>
        </>
      )}

      <div className="flex gap-3">
        <button onClick={importNow} disabled={busy || !preview} className="btn-primary">
          {busy && preview
            ? 'Importing…'
            : preview
              ? `Import ${months.length} month${months.length === 1 ? '' : 's'}`
              : 'Import'}
        </button>
        <button onClick={onCancel} disabled={busy && Boolean(preview)} className="btn-secondary">
          Cancel
        </button>
      </div>
    </div>
  );
}

export default MeterReportImport;
