import { formatMoney, meterBill } from '../format';

// Prepaid main meter money for a month: opening balance + recharge - closing
// balance = what the meter deducted, which becomes the Monthly Bill.
// onChange(field, value) with field one of the meter_* names.
// idPrefix keeps input ids unique when two of these are on the page.
function MeterBalanceFields({
  opening,
  recharge,
  closing,
  onChange,
  disabled = false,
  openingHint = null,
  idPrefix = 'meter',
}) {
  const bill = meterBill(opening, recharge, closing);
  const field = (name, label, value, extra = {}) => (
    <div className="flex flex-col gap-1">
      <label htmlFor={`${idPrefix}-${name}`} className="text-xs font-medium text-slate-500">
        {label}
      </label>
      <input
        id={`${idPrefix}-${name}`}
        type="number"
        step="0.01"
        value={value ?? ''}
        disabled={disabled}
        onChange={(e) => onChange(name, e.target.value)}
        {...extra}
      />
    </div>
  );

  return (
    <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50/60 p-4">
      <p className="mb-3 text-sm font-medium text-slate-700">
        Prepaid meter <span className="font-normal text-slate-500">(optional: fills in the Monthly Bill)</span>
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {field('meter_opening_balance', 'Opening balance', opening, { placeholder: 'e.g. 1795.19' })}
        {field('meter_recharge', 'Recharge', recharge, { min: '0', placeholder: 'e.g. 4500' })}
        {field('meter_closing_balance', 'Closing balance', closing, { placeholder: 'e.g. 225.71' })}
      </div>
      <p className="mt-3 text-sm text-slate-600">
        {bill === null ? (
          <>
            {openingHint && <span className="mr-2 text-slate-500">Opening: {openingHint}.</span>}
            Enter all three to work out the bill: opening + recharge − closing.
          </>
        ) : bill < 0 ? (
          <span className="text-rose-600">
            The closing balance is more than opening + recharge. Check the numbers.
          </span>
        ) : (
          <>
            {formatMoney(Number(opening))} + {formatMoney(Number(recharge))} − {formatMoney(Number(closing))} ={' '}
            <span className="font-semibold">{formatMoney(bill)} deducted</span> (Monthly Bill). The closing
            balance carries forward to next month.
          </>
        )}
      </p>
    </div>
  );
}

export default MeterBalanceFields;
