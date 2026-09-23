function MonthSelector({ months, selectedMonth, onChange }) {
  const sorted = [...months].sort((a, b) => (a.month > b.month ? -1 : 1));

  return (
    <div className="flex items-center gap-3">
      <label htmlFor="month-select" className="text-sm font-medium text-slate-600">
        Month
      </label>
      <select
        id="month-select"
        value={selectedMonth || ''}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-[10rem]"
      >
        <option value="" disabled>
          Select a month
        </option>
        {sorted.map((m) => (
          <option key={m.month} value={m.month}>
            {m.month}
          </option>
        ))}
      </select>
    </div>
  );
}

export default MonthSelector;
