import { formatMoney, formatMonth, formatNumber } from '../format';

// Everything so far, per roommate: what they recharged, the units they used
// (own meter + share of common), what that cost, and what's left over.
// balances: /api/history rows. months: to show what's left in the meter.
function TotalsTable({ balances, months }) {
  if (balances.length === 0) {
    return <p className="text-sm text-slate-500">Totals show up after the first month is billed.</p>;
  }
  // Left over = recharged − billed (± settle-up payments): positive is money left, negative is due.
  const left = (b) => -b.balance;
  const sum = (key) => balances.reduce((total, b) => total + (Number(b[key]) || 0), 0);
  const totalLeft = balances.reduce((total, b) => total + left(b), 0);
  // The latest month with a closing balance (months may come in any order).
  const lastMeter = months
    .filter((m) => m.meter_closing_balance != null)
    .sort((a, b) => a.month.localeCompare(b.month))
    .at(-1);

  const leftCell = (amount) => (
    <span className={amount > 0.004 ? 'text-emerald-700' : amount < -0.004 ? 'text-rose-600' : ''}>
      {formatMoney(Math.abs(amount))}
      <span className="ml-1 text-xs font-normal">{amount > 0.004 ? 'left' : amount < -0.004 ? 'due' : ''}</span>
    </span>
  );

  return (
    <div>
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Roommate</th>
              <th className="text-right">Recharged</th>
              <th className="text-right">Units used</th>
              <th className="text-right">Bill</th>
              <th className="text-right">Balance left</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {balances.map((b) => (
              <tr key={b.roommate_id}>
                <td className="font-medium">{b.name}</td>
                <td className="text-right tabular-nums">
                  {formatMoney(b.total_recharges_cumulative)}
                  {b.dg_recharges_cumulative > 0 && (
                    <span className="block text-xs text-slate-500">DG {formatMoney(b.dg_recharges_cumulative)}</span>
                  )}
                </td>
                <td className="text-right tabular-nums">
                  {formatNumber(b.units_cumulative)}
                  <span className="block text-xs text-slate-500">
                    own {formatNumber(b.own_units_cumulative)}
                  </span>
                </td>
                <td className="text-right tabular-nums">{formatMoney(b.total_bill_cumulative)}</td>
                <td className="text-right font-medium tabular-nums">
                  {leftCell(left(b))}
                  {b.settled_cumulative !== 0 && b.settled_cumulative != null && (
                    <span className="block text-xs font-normal text-slate-500">
                      {b.settled_cumulative > 0 ? 'paid back' : 'received'} {formatMoney(Math.abs(b.settled_cumulative))}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t-2 border-slate-300 bg-slate-50">
            <tr>
              <td className="font-semibold">Total</td>
              <td className="text-right font-semibold tabular-nums">{formatMoney(sum('total_recharges_cumulative'))}</td>
              <td className="text-right font-semibold tabular-nums">{formatNumber(sum('units_cumulative'))}</td>
              <td className="text-right font-semibold tabular-nums">{formatMoney(sum('total_bill_cumulative'))}</td>
              <td className="text-right font-semibold tabular-nums">{leftCell(totalLeft)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      {lastMeter && (
        <p className="mt-3 text-sm text-slate-500">
          In the meter after {formatMonth(lastMeter.month)}:{' '}
          <span className="font-medium text-slate-700">{formatMoney(lastMeter.meter_closing_balance)}</span>
          {' '}(its closing balance). With every recharge recorded, the total left over matches this, plus anything
          recharged since.
        </p>
      )}
    </div>
  );
}

export default TotalsTable;
