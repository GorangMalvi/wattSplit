import { useEffect, useMemo, useState } from 'react';
import {
  getMonths,
  getMonth,
  createMonth,
  updateMonth,
  getRoommates,
  createRoommate,
  updateRoommate,
  getCalculate,
  getHistory,
  getRecharges,
  createRecharge,
  updateRecharge,
  deleteRecharge,
  updateReading,
  downloadExport,
} from './api';
import MonthSelector from './components/MonthSelector';
import NewMonthForm from './components/NewMonthForm';
import RoommatesTable from './components/RoommatesTable';
import SummaryCard from './components/SummaryCard';
import ReadingsTable from './components/ReadingsTable';
import RechargesTable from './components/RechargesTable';
import BillSplitTable from './components/BillSplitTable';
import BalanceCard from './components/BalanceCard';
import LoadingSpinner from './components/LoadingSpinner';
import ErrorAlert from './components/ErrorAlert';

function formatMoney(value) {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  return `₹${Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatNumber(value, digits = 2) {
  if (value === undefined || value === null || Number.isNaN(value)) return '—';
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
}

// Mirrors calc._roommate_is_active on the backend.
function isActiveIn(roommate, month) {
  const join = roommate.join_date || '';
  const leave = roommate.leave_date || '';
  if (!roommate.is_active) return Boolean(leave) && month <= leave;
  if (join && month < join) return false;
  if (leave && month > leave) return false;
  return true;
}

function App() {
  const [months, setMonths] = useState([]);
  const [roommates, setRoommates] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [monthData, setMonthData] = useState(null);
  const [calcData, setCalcData] = useState(null);
  const [recharges, setRecharges] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [showNewMonth, setShowNewMonth] = useState(false);

  const selectedMonthDetails = useMemo(
    () => months.find((m) => m.month === selectedMonth) || null,
    [months, selectedMonth]
  );

  const loadInitial = async (monthToSelect) => {
    setLoading(true);
    setError(null);
    try {
      const [monthsRes, roommatesRes, historyRes] = await Promise.all([
        getMonths(),
        getRoommates(),
        getHistory(),
      ]);
      const sortedMonths = [...monthsRes].sort((a, b) => (a.month > b.month ? -1 : 1));
      setMonths(sortedMonths);
      setRoommates(roommatesRes);
      setHistory(historyRes);
      if (monthToSelect) {
        setSelectedMonth(monthToSelect);
      } else if (sortedMonths.length > 0) {
        setSelectedMonth(sortedMonths[0].month);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadMonthData = async (month) => {
    if (!month) return;
    setLoading(true);
    setError(null);
    try {
      const [monthRes, calcRes, rechargesRes, historyRes] = await Promise.all([
        getMonth(month),
        // No split yet for a month without readings; that's not an error.
        getCalculate(month).catch(() => null),
        getRecharges(month),
        getHistory(),
      ]);
      setMonthData(monthRes);
      setCalcData(calcRes);
      setRecharges(rechargesRes);
      setHistory(historyRes);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInitial();
  }, []);

  useEffect(() => {
    if (selectedMonth) {
      loadMonthData(selectedMonth);
    }
  }, [selectedMonth]);

  const handleMonthChange = (month) => {
    setSelectedMonth(month);
  };

  const handleMonthFieldChange = (field, value) => {
    setMonthData((prev) => (prev ? { ...prev, [field]: value } : prev));
  };

  const saveMonthDetails = async () => {
    if (!selectedMonth || !monthData) return;
    setSaving(true);
    try {
      const payload = {
        main_start_reading: parseFloat(monthData.main_start_reading) || 0,
        main_end_reading: parseFloat(monthData.main_end_reading) || 0,
        monthly_bill: parseFloat(monthData.monthly_bill) || 0,
        dg_bill: parseFloat(monthData.dg_bill) || 0,
        notes: monthData.notes || '',
      };
      await updateMonth(selectedMonth, payload);
      await loadMonthData(selectedMonth);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleReadingUpdate = async (roommateId, currentReading) => {
    if (!selectedMonth) return;
    setSaving(true);
    try {
      await updateReading(selectedMonth, roommateId, currentReading);
      await loadMonthData(selectedMonth);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleRechargeSave = async (recharge) => {
    if (!selectedMonth) return;
    setSaving(true);
    try {
      if (recharge.id) {
        await updateRecharge(recharge.id, recharge);
      } else {
        await createRecharge(recharge);
      }
      const [rechargesRes, calcRes] = await Promise.all([
        getRecharges(selectedMonth),
        getCalculate(selectedMonth).catch(() => null),
      ]);
      setRecharges(rechargesRes);
      setCalcData(calcRes);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleRechargeDelete = async (id) => {
    if (!selectedMonth) return;
    setSaving(true);
    try {
      await deleteRecharge(id);
      const [rechargesRes, calcRes] = await Promise.all([
        getRecharges(selectedMonth),
        getCalculate(selectedMonth).catch(() => null),
      ]);
      setRecharges(rechargesRes);
      setCalcData(calcRes);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleExport = async () => {
    if (!selectedMonth) return;
    try {
      await downloadExport(selectedMonth);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCreateMonth = async (payload) => {
    setSaving(true);
    try {
      const created = await createMonth(payload);
      setShowNewMonth(false);
      await loadInitial(created.month);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleRoommateAdd = async (payload) => {
    setSaving(true);
    try {
      const created = await createRoommate(payload);
      setRoommates((prev) => [...prev, created]);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleRoommateUpdate = async (id, payload) => {
    setSaving(true);
    try {
      const updated = await updateRoommate(id, payload);
      setRoommates((prev) => prev.map((r) => (r.id === id ? updated : r)));
      if (selectedMonth) await loadMonthData(selectedMonth);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const summary = calcData?.summary || {};
  const splitRows = calcData?.roommates || [];
  // One row per roommate active this month (or with a stored reading), so
  // readings can be entered before the first split exists.
  const readingRows = useMemo(() => {
    const splitById = Object.fromEntries(splitRows.map((r) => [r.roommate_id, r]));
    const readingById = Object.fromEntries(
      (monthData?.readings || []).map((r) => [r.roommate_id, r.current_reading])
    );
    return roommates
      .filter((rm) => readingById[rm.id] !== undefined || isActiveIn(rm, selectedMonth))
      .map((rm) => ({
        roommate_id: rm.id,
        name: rm.name,
        previous_reading: splitById[rm.id]?.previous_reading ?? null,
        current_reading: readingById[rm.id] ?? null,
        sub_units: splitById[rm.id]?.sub_units ?? null,
      }));
  }, [roommates, monthData, splitRows, selectedMonth]);

  const selectedMonthBalances = splitRows.map((r) => ({
    id: r.roommate_id,
    name: r.name,
    balance: r.balance ?? 0,
  }));

  return (
    <div className="min-h-screen bg-slate-50 p-4 md:p-6 lg:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Electricity Bill Splitter</h1>
            <p className="text-sm text-slate-500">Manage readings, recharges and monthly splits.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <MonthSelector
              months={months}
              selectedMonth={selectedMonth}
              onChange={handleMonthChange}
            />
            <button
              onClick={() => setShowNewMonth(true)}
              disabled={loading || showNewMonth}
              className="btn-secondary"
            >
              New Month
            </button>
            <button
              onClick={handleExport}
              disabled={!selectedMonth || loading}
              className="btn-primary"
            >
              Export Report
            </button>
          </div>
        </div>

        {error && <ErrorAlert message={error} onRetry={() => loadMonthData(selectedMonth)} />}

        {(showNewMonth || (!loading && months.length === 0)) && (
          <NewMonthForm
            months={months}
            onCreate={handleCreateMonth}
            onCancel={months.length > 0 ? () => setShowNewMonth(false) : null}
            loading={saving}
          />
        )}

        {loading && months.length === 0 ? (
          <LoadingSpinner />
        ) : months.length === 0 ? (
          <div className="card">
            <h2 className="mb-1 text-lg font-semibold text-slate-900">Roommates</h2>
            <p className="mb-4 text-sm text-slate-500">
              Add everyone who shares the bill, then create your first month above.
            </p>
            <RoommatesTable
              roommates={roommates}
              onAdd={handleRoommateAdd}
              onUpdate={handleRoommateUpdate}
              loading={saving}
            />
          </div>
        ) : (
          <>
            {/* Summary Cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <SummaryCard
                label="Main Units"
                value={formatNumber(summary.main_units)}
                subtext={`Start: ${formatNumber(monthData?.main_start_reading, 2)} → End: ${formatNumber(
                  monthData?.main_end_reading,
                  2
                )}`}
              />
              <SummaryCard
                label="Rate per Unit"
                value={formatMoney(summary.rate_per_unit)}
                subtext="Monthly bill ÷ main units"
              />
              <SummaryCard
                label="Total Bill"
                value={formatMoney(summary.total_bill)}
                subtext="Main electricity bill"
              />
              <SummaryCard
                label="DG Bill"
                value={formatMoney(summary.dg_bill)}
                subtext="Split equally among active roommates"
              />
            </div>

            {/* Month details form */}
            <div className="card">
              <h2 className="mb-4 text-lg font-semibold text-slate-900">Monthly Inputs</h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-slate-500">Month</label>
                  <input value={selectedMonthDetails?.month || ''} disabled />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-slate-500">Main Start Reading</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={monthData?.main_start_reading ?? ''}
                    onChange={(e) => handleMonthFieldChange('main_start_reading', e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-slate-500">Main End Reading</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={monthData?.main_end_reading ?? ''}
                    onChange={(e) => handleMonthFieldChange('main_end_reading', e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-slate-500">Monthly Bill</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={monthData?.monthly_bill ?? ''}
                    onChange={(e) => handleMonthFieldChange('monthly_bill', e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-slate-500">DG Bill</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={monthData?.dg_bill ?? ''}
                    onChange={(e) => handleMonthFieldChange('dg_bill', e.target.value)}
                  />
                </div>
              </div>
              <div className="mt-4 flex items-center gap-3">
                <button
                  onClick={saveMonthDetails}
                  disabled={saving || !selectedMonth}
                  className="btn-primary"
                >
                  {saving ? 'Saving…' : 'Save Month Details'}
                </button>
              </div>
            </div>

            {/* Readings */}
            <div className="card">
              <h2 className="mb-4 text-lg font-semibold text-slate-900">Meter Readings</h2>
              {loading ? (
                <LoadingSpinner />
              ) : (
                <ReadingsTable
                  rows={readingRows}
                  onUpdate={handleReadingUpdate}
                  loading={saving}
                />
              )}
            </div>

            {/* Recharges */}
            <div className="card">
              <h2 className="mb-4 text-lg font-semibold text-slate-900">Recharges / Payments</h2>
              {loading ? (
                <LoadingSpinner />
              ) : (
                <RechargesTable
                  recharges={recharges}
                  roommates={roommates}
                  month={selectedMonth}
                  onSave={handleRechargeSave}
                  onDelete={handleRechargeDelete}
                  loading={saving}
                />
              )}
            </div>

            {/* Bill Split */}
            <div className="card">
              <h2 className="mb-4 text-lg font-semibold text-slate-900">Bill Split</h2>
              {loading ? <LoadingSpinner /> : <BillSplitTable rows={splitRows} />}
            </div>

            {/* Roommates */}
            <div className="card">
              <h2 className="mb-4 text-lg font-semibold text-slate-900">Roommates</h2>
              <RoommatesTable
                roommates={roommates}
                onAdd={handleRoommateAdd}
                onUpdate={handleRoommateUpdate}
                loading={saving}
              />
            </div>

            {/* Balances */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="card">
                <h2 className="mb-4 text-lg font-semibold text-slate-900">
                  Selected Month Balances
                </h2>
                {selectedMonthBalances.length > 0 ? (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {selectedMonthBalances.map((b) => (
                      <BalanceCard key={b.id} name={b.name} balance={b.balance} />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-slate-500">No balance data for this month.</p>
                )}
              </div>

              <div className="card">
                <h2 className="mb-4 text-lg font-semibold text-slate-900">Running Balances</h2>
                {history.length > 0 ? (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {history.map((h) => (
                      <BalanceCard key={h.roommate_id || h.id} name={h.name} balance={h.balance} />
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-slate-500">No running balance history available.</p>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default App;
