// detail: optional extra line under the label (e.g. per-meter balances).
function BalanceCard({ name, balance, detail }) {
  const isPositive = balance > 0;
  const isNegative = balance < 0;
  const colorClass = isPositive
    ? 'bg-rose-50 text-rose-700 border-rose-200'
    : isNegative
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : 'bg-slate-50 text-slate-700 border-slate-200';

  const label = isPositive ? 'Owes' : isNegative ? 'Credit' : 'Settled';

  return (
    <div className={`rounded-xl border p-4 ${colorClass}`}>
      <p className="text-sm font-medium">{name}</p>
      <p className="mt-1 text-xl font-bold tabular-nums">
        ₹{Math.abs(balance).toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}
      </p>
      <p className="mt-1 text-xs opacity-80">{label}</p>
      {detail && <p className="mt-1 text-xs opacity-80">{detail}</p>}
    </div>
  );
}

export default BalanceCard;
