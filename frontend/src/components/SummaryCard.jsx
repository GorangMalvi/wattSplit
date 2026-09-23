function SummaryCard({ label, value, subtext }) {
  return (
    <div className="card flex flex-col">
      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <span className="mt-1 text-2xl font-bold text-slate-900">{value}</span>
      {subtext && <span className="mt-1 text-xs text-slate-500">{subtext}</span>}
    </div>
  );
}

export default SummaryCard;
