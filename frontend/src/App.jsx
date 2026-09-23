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
  getMe,
  unlinkRoommate,
  getInvites,
  inviteRoommate,
  revokeInvite,
} from './api';
import { formatMoney, formatNumber, meterBill } from './format';
import MonthSelector from './components/MonthSelector';
import NewMonthForm from './components/NewMonthForm';
import MeterReportImport from './components/MeterReportImport';
import MeterBalanceFields from './components/MeterBalanceFields';
import RoommatesTable from './components/RoommatesTable';
import SummaryCard from './components/SummaryCard';
import ReadingsTable from './components/ReadingsTable';
import RechargesTable from './components/RechargesTable';
import BillSplitTable from './components/BillSplitTable';
import BalanceCard from './components/BalanceCard';
import LoadingSpinner from './components/LoadingSpinner';
import ErrorAlert from './components/ErrorAlert';
import MyDashboard, { LinkRoommateCard } from './components/MyDashboard';

// Mirrors calc._roommate_is_active on the backend.
function isActiveIn(roommate, month) {
  const join = roommate.join_date || '';
  const leave = roommate.leave_date || '';
  if (!roommate.is_active) return Boolean(leave) && month <= leave;
  if (join && month < join) return false;
  if (leave && month > leave) return false;
  return true;
}

// Last tab the user had open, so a page refresh returns to it.
const VIEW_KEY = 'wattsplit.view';

function readStoredView() {
  try {
    return localStorage.getItem(VIEW_KEY) === 'household' ? 'household' : 'mine';
  } catch {
    return 'mine';
  }
}

function storeView(view) {
  try {
    localStorage.setItem(VIEW_KEY, view);
  } catch {
    // Storage unavailable (private mode etc.): just don't remember it.
  }
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
  const [showImport, setShowImport] = useState(false);
  // Signed-in user's role and linked roommate; 'mine' = personal dashboard.
  const [me, setMe] = useState(null);
  const [invites, setInvites] = useState([]); // owner: pending roommate invites
  const [view, setView] = useState(readStoredView);

  const isOwner = me?.role === 'owner';
  const myRoommateId = me?.roommate?.id;
  const canEdit = (roommateId) => isOwner || roommateId === myRoommateId;

  const selectedMonthDetails = useMemo(
    () => months.find((m) => m.month === selectedMonth) || null,
    [months, selectedMonth]
  );

  const loadInitial = async (monthToSelect) => {
    setLoading(true);
    setError(null);
    try {
      const [monthsRes, roommatesRes, historyRes, meRes] = await Promise.all([
        getMonths(),
        getRoommates(),
        getHistory(),
        getMe(),
      ]);
      setMe(meRes);
      if (meRes.role === 'owner') setInvites(await getInvites());
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

  // quiet: refresh in place, keeping what's on screen instead of spinners.
  const loadMonthData = async (month, { quiet = false } = {}) => {
    if (!month) return;
    if (!quiet) setLoading(true);
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

  const switchView = (next) => {
    setView(next);
    storeView(next);
    // Readings/payments may have changed on the dashboard.
    if (next === 'household' && selectedMonth) loadMonthData(selectedMonth, { quiet: true });
  };

  const handleLinkChange = async (nextMe) => {
    setMe(nextMe ?? { ...me, roommate: null });
    try {
      setRoommates(await getRoommates());
    } catch (err) {
      setError(err.message);
    }
  };

  const handleUnlink = async (roommateId) => {
    setSaving(true);
    try {
      await unlinkRoommate(roommateId);
      const [roommatesRes, meRes] = await Promise.all([getRoommates(), getMe()]);
      setRoommates(roommatesRes);
      setMe(meRes);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleMonthFieldChange = (field, value) => {
    setMonthData((prev) => (prev ? { ...prev, [field]: value } : prev));
  };

  const saveMonthDetails = async () => {
    if (!selectedMonth || !monthData) return;
    setSaving(true);
    try {
      const optional = (v) => (v === '' || v === null || v === undefined ? null : parseFloat(v));
      const payload = {
        main_start_reading: parseFloat(monthData.main_start_reading) || 0,
        main_end_reading: parseFloat(monthData.main_end_reading) || 0,
        monthly_bill:
          monthMeterBill !== null && monthMeterBill >= 0
            ? monthMeterBill
            : parseFloat(monthData.monthly_bill) || 0,
        dg_bill: parseFloat(monthData.dg_bill) || 0,
        notes: monthData.notes || '',
        // Blank clears; with all three set the backend works out monthly_bill.
        meter_opening_balance: optional(monthData.meter_opening_balance),
        meter_recharge: optional(monthData.meter_recharge),
        meter_closing_balance: optional(monthData.meter_closing_balance),
      };
      const updated = await updateMonth(selectedMonth, payload);
      // Keep the month list current: New Month carries the closing balance from it.
      setMonths((prev) => prev.map((m) => (m.month === updated.month ? updated : m)));
      await loadMonthData(selectedMonth);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // fields: { current_reading } or { start_reading }; null clears it.
  const handleReadingUpdate = async (roommateId, fields) => {
    if (!selectedMonth) return;
    setSaving(true);
    try {
      await updateReading(selectedMonth, roommateId, fields);
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

  const handleMeterImported = async (imported) => {
    setShowImport(false);
    const latest = imported[imported.length - 1]?.month;
    await loadInitial(latest);
    // Same month still selected: its effect won't re-run, so reload it here.
    if (latest === selectedMonth) await loadMonthData(latest);
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

  // email: optional; when given the new roommate is invited straight away.
  const handleRoommateAdd = async (payload, email) => {
    setSaving(true);
    try {
      const created = await createRoommate(payload);
      setRoommates((prev) => [...prev, created]);
      if (!email) return { roommate: created };
      const invite = await inviteRoommate(created.id, email);
      setInvites(await getInvites());
      return { roommate: created, invite };
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setSaving(false);
    }
  };

  const handleInvite = async (roommateId, email) => {
    try {
      const invite = await inviteRoommate(roommateId, email);
      setInvites(await getInvites());
      return invite;
    } catch (err) {
      setError(err.message);
      return null;
    }
  };

  const handleRevokeInvite = async (inviteId) => {
    try {
      await revokeInvite(inviteId);
      setInvites(await getInvites());
    } catch (err) {
      setError(err.message);
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

  // Prepaid meter balances entered for the selected month -> its bill (or null).
  const monthMeterBill = meterBill(
    monthData?.meter_opening_balance,
    monthData?.meter_recharge,
    monthData?.meter_closing_balance
  );
  const previousMonth = months.find((m) => m.month < selectedMonth);
  const hasMeterBalances = ['meter_opening_balance', 'meter_recharge', 'meter_closing_balance'].some(
    (f) => monthData?.[f] !== null && monthData?.[f] !== undefined && monthData?.[f] !== ''
  );

  // Before any sub-meter reading there's no split, but the month summary only
  // needs the main meter and bill (same formulas as calc._split_month).
  const summary = useMemo(() => {
    if (calcData?.summary) return calcData.summary;
    if (!monthData) return {};
    const start = Number(monthData.main_start_reading) || 0;
    const end = Number(monthData.main_end_reading) || start;
    const bill = Number(monthData.monthly_bill) || 0;
    const dg = Number(monthData.dg_bill) || 0;
    const units = end - start;
    return {
      main_units: units,
      rate_per_unit: units ? bill / units : 0,
      total_bill: bill + dg,
      dg_bill: dg,
    };
  }, [calcData, monthData]);
  const splitRows = calcData?.roommates || [];
  // One row per roommate active this month (or with a stored reading), so
  // readings can be entered before the first split exists.
  const readingRows = useMemo(() => {
    const splitById = Object.fromEntries(splitRows.map((r) => [r.roommate_id, r]));
    const readingById = Object.fromEntries((monthData?.readings || []).map((r) => [r.roommate_id, r]));
    // Last month's month-end reading is this month's start; without one the
    // start reading entered for this month is used (same rule as the backend).
    const carriedById = Object.fromEntries(
      (monthData?.previous_readings || []).map((r) => [r.roommate_id, r.current_reading])
    );
    return roommates
      .filter((rm) => readingById[rm.id] !== undefined || isActiveIn(rm, selectedMonth))
      .map((rm) => {
        const carried = carriedById[rm.id];
        const start = readingById[rm.id]?.start_reading ?? null;
        const previous = carried ?? start;
        const current = readingById[rm.id]?.current_reading ?? null;
        return {
          roommate_id: rm.id,
          name: rm.name,
          previous_reading: previous,
          previous_editable: carried === undefined,
          start_reading: start,
          current_reading: current,
          sub_units:
            splitById[rm.id]?.sub_units ??
            (current !== null && previous !== null ? current - previous : null),
        };
      });
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
          <div className="inline-flex self-start rounded-lg bg-slate-200/70 p-1" role="tablist">
            {[
              ['mine', 'My dashboard'],
              ['household', 'Household'],
            ].map(([key, label]) => (
              <button
                key={key}
                role="tab"
                aria-selected={view === key}
                onClick={() => switchView(key)}
                className={
                  view === key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                }
              >
                {label}
              </button>
            ))}
          </div>
          {view === 'household' && (
            <div className="flex flex-wrap items-center gap-3">
              <MonthSelector
                months={months}
                selectedMonth={selectedMonth}
                onChange={handleMonthChange}
              />
              {isOwner && (
                <button
                  onClick={() => setShowNewMonth(true)}
                  disabled={loading || showNewMonth}
                  className="btn-secondary"
                >
                  New Month
                </button>
              )}
              {isOwner && (
                <button
                  onClick={() => setShowImport(true)}
                  disabled={loading || showImport}
                  className="btn-secondary"
                >
                  Import meter report
                </button>
              )}
              <button
                onClick={handleExport}
                disabled={!selectedMonth || loading}
                className="btn-primary"
              >
                Export Report
              </button>
            </div>
          )}
        </div>

        {error && <ErrorAlert message={error} onRetry={() => loadInitial(selectedMonth)} />}

        {/* Stays mounted while on the Household tab, so coming back is instant. */}
        {me?.roommate && (
          <div hidden={view !== 'mine'}>
            <MyDashboard
              key={me.roommate.id}
              active={view === 'mine'}
              roommates={roommates}
              onLinkChange={handleLinkChange}
            />
          </div>
        )}

        {view === 'mine' ? (
          !me ? (
            <LoadingSpinner />
          ) : me.roommate ? null : (
            <LinkRoommateCard roommates={roommates} onLinked={handleLinkChange} />
          )
        ) : (
          <>
            {isOwner && showImport && (
              <MeterReportImport
                onImported={handleMeterImported}
                onCancel={() => setShowImport(false)}
              />
            )}

            {isOwner && !showImport && (showNewMonth || (!loading && months.length === 0)) && (
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
                  {isOwner
                    ? 'Add everyone who shares the bill, then create your first month above.'
                    : 'The household owner has not started a billing month yet.'}
                </p>
                <RoommatesTable
                  roommates={roommates}
                  onAdd={handleRoommateAdd}
                  onUpdate={handleRoommateUpdate}
                  onUnlink={handleUnlink}
                  invites={invites}
                  onInvite={isOwner ? handleInvite : undefined}
                  onRevokeInvite={handleRevokeInvite}
                  readOnly={!isOwner}
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
                        disabled={!isOwner}
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
                        disabled={!isOwner}
                        onChange={(e) => handleMonthFieldChange('main_end_reading', e.target.value)}
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-xs font-medium text-slate-500">
                        Monthly Bill (amount deducted)
                      </label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={monthMeterBill ?? monthData?.monthly_bill ?? ''}
                        disabled={!isOwner}
                        readOnly={monthMeterBill !== null}
                        title={monthMeterBill !== null ? 'Worked out from the prepaid meter balances' : undefined}
                        className={monthMeterBill !== null ? 'bg-slate-50' : ''}
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
                        disabled={!isOwner}
                        onChange={(e) => handleMonthFieldChange('dg_bill', e.target.value)}
                      />
                    </div>
                  </div>
                  {/* Only once the month is loaded, so typing isn't overwritten by it. */}
                  {monthData?.month === selectedMonth && (isOwner || hasMeterBalances) && (
                    <MeterBalanceFields
                      opening={monthData?.meter_opening_balance}
                      recharge={monthData?.meter_recharge}
                      closing={monthData?.meter_closing_balance}
                      onChange={handleMonthFieldChange}
                      disabled={!isOwner}
                      idPrefix="month"
                      openingHint={
                        previousMonth?.meter_closing_balance != null
                          ? `${formatMoney(previousMonth.meter_closing_balance)} was ${previousMonth.month}'s closing balance`
                          : null
                      }
                    />
                  )}
                  {isOwner ? (
                    <div className="mt-4 flex items-center gap-3">
                      <button
                        onClick={saveMonthDetails}
                        disabled={saving || !selectedMonth}
                        className="btn-primary"
                      >
                        {saving ? 'Saving…' : 'Save Month Details'}
                      </button>
                    </div>
                  ) : (
                    <p className="mt-4 text-xs text-slate-500">
                      Only the household owner can change the main meter and bill amounts.
                    </p>
                  )}
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
                      canEdit={canEdit}
                      mainUnits={summary.main_units ?? null}
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
                      canEdit={canEdit}
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
                    onUnlink={handleUnlink}
                    invites={invites}
                    onInvite={isOwner ? handleInvite : undefined}
                    onRevokeInvite={handleRevokeInvite}
                    readOnly={!isOwner}
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
                    <h2 className="mb-4 text-lg font-semibold text-slate-900">Balances to Date</h2>
                    {history.length > 0 ? (
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {history.map((h) => (
                          <BalanceCard
                            key={h.roommate_id || h.id}
                            name={h.name}
                            balance={h.balance}
                            detail={`Main ${formatMoney(h.main_balance)} · DG ${formatMoney(h.dg_balance)}`}
                          />
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-slate-500">No running balance history available.</p>
                    )}
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default App;
