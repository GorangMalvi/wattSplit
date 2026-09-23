function formatMoney(value) {
  if (value === undefined || value === null) return '-';
  return `₹${value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatNumber(value, digits = 2) {
  if (value === undefined || value === null) return '-';
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function BillSplitTable({ rows }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Roommate</th>
            <th className="text-right">Sub Units</th>
            <th className="text-right">Common Share</th>
            <th className="text-right">Total Units</th>
            <th className="text-right">Energy Charge</th>
            <th className="text-right">DG Share</th>
            <th className="text-right">Total Bill</th>
            <th className="text-right">Recharges</th>
            <th className="text-right">Balance</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {rows.map((row) => {
            const balance = row.balance ?? 0;
            const balanceClass =
              balance > 0 ? 'text-rose-600' : balance < 0 ? 'text-emerald-600' : 'text-slate-700';

            return (
              <tr key={row.roommate_id}>
                <td className="font-medium">{row.name}</td>
                <td className="text-right tabular-nums">{formatNumber(row.sub_units)}</td>
                <td className="text-right tabular-nums">{formatNumber(row.common_share)}</td>
                <td className="text-right tabular-nums">{formatNumber(row.total_units)}</td>
                <td className="text-right tabular-nums">{formatMoney(row.energy_charge)}</td>
                <td className="text-right tabular-nums">{formatMoney(row.dg_share)}</td>
                <td className="text-right tabular-nums font-medium">
                  {formatMoney(row.total_bill)}
                </td>
                <td className="text-right tabular-nums">{formatMoney(row.recharges)}</td>
                <td className={`text-right tabular-nums font-semibold ${balanceClass}`}>
                  {formatMoney(balance)}
                </td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={9} className="py-6 text-center text-slate-500">
                No data available for this month.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default BillSplitTable;
