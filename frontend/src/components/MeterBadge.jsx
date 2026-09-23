// Which meter a payment went to: the main grid meter or the DG (generator).
export const METERS = [
  ['main', 'Main meter'],
  ['dg', 'DG'],
];

function MeterBadge({ meter }) {
  const dg = meter === 'dg';
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        dg ? 'bg-amber-50 text-amber-700' : 'bg-indigo-50 text-indigo-700'
      }`}
    >
      {dg ? 'DG' : 'Main'}
    </span>
  );
}

export default MeterBadge;
