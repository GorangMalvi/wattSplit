import { Fragment, useState } from 'react';

const currentMonth = () => new Date().toISOString().slice(0, 7);
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function CopyButton({ text, label }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked: the text is on screen to copy by hand.
    }
  };
  return (
    <button type="button" onClick={copy} className="btn-secondary px-2 py-1 text-xs">
      {copied ? 'Copied' : label}
    </button>
  );
}

// What was sent: email status plus the link/code to share another way.
function InviteResult({ invite, onClose }) {
  return (
    <div className="space-y-2 rounded-lg border border-indigo-100 bg-indigo-50/60 p-3 text-sm">
      {invite.email_sent === false ? (
        <p className="text-amber-700">
          Couldn't email {invite.email}
          {invite.email_error ? ` (${invite.email_error})` : ''}. Share the link or code yourself.
        </p>
      ) : invite.email_sent ? (
        <p className="text-emerald-700">Invite emailed to {invite.email}.</p>
      ) : (
        <p className="text-slate-600">Invite for {invite.email}.</p>
      )}
      {invite.link && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-slate-500">Link:</span>
          <code className="break-all rounded bg-white px-2 py-1 text-xs">{invite.link}</code>
          <CopyButton text={invite.link} label="Copy link" />
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-slate-500">Code:</span>
        <code className="rounded bg-white px-2 py-1 font-mono tracking-widest">{invite.code}</code>
        <CopyButton text={invite.code} label="Copy code" />
        <span className="text-xs text-slate-500">
          (wattSplit → Join with a code, signed in as {invite.email})
        </span>
      </div>
      <button type="button" onClick={onClose} className="btn-secondary px-2 py-1 text-xs">
        Done
      </button>
    </div>
  );
}

// readOnly: members see the list; only the owner edits it. onUnlink: owner detaches a login.
// Owner only: invites (pending, by roommate), onInvite(roommateId, email) -> invite,
// onRevokeInvite(inviteId). onAdd(payload, email) may return { invite } when an email was given.
function RoommatesTable({
  roommates,
  onAdd,
  onUpdate,
  onUnlink,
  loading,
  readOnly = false,
  invites = [],
  onInvite,
  onRevokeInvite,
}) {
  const [newRoommate, setNewRoommate] = useState({ name: '', join_date: currentMonth(), email: '' });
  const [inviteFor, setInviteFor] = useState(null); // roommate id with the email form open
  const [inviteEmail, setInviteEmail] = useState('');
  const [sending, setSending] = useState(false);
  const [results, setResults] = useState({}); // roommate id -> last invite sent
  const canInvite = !readOnly && Boolean(onInvite);
  const columns = canInvite ? 5 : 4;
  const pendingFor = (id) => invites.find((i) => i.roommate_id === id);

  const save = (roommate, changes) => {
    onUpdate(roommate.id, {
      name: roommate.name,
      join_date: roommate.join_date,
      leave_date: roommate.leave_date,
      is_active: roommate.is_active,
      ...changes,
    });
  };

  const addNew = async () => {
    const name = newRoommate.name.trim();
    const email = newRoommate.email.trim();
    if (!name || (email && !EMAIL_RE.test(email))) return;
    setNewRoommate({ name: '', join_date: currentMonth(), email: '' });
    const added = await onAdd(
      { name, join_date: newRoommate.join_date, leave_date: '', is_active: true },
      email || null
    );
    if (added?.invite) setResults((r) => ({ ...r, [added.roommate.id]: added.invite }));
  };

  const openInvite = (rm) => {
    setInviteFor(rm.id);
    setInviteEmail(pendingFor(rm.id)?.email || '');
  };

  const sendInvite = async (e) => {
    e.preventDefault();
    if (!EMAIL_RE.test(inviteEmail.trim())) return;
    setSending(true);
    const invite = await onInvite(inviteFor, inviteEmail.trim());
    setSending(false);
    if (invite) {
      setResults((r) => ({ ...r, [inviteFor]: invite }));
      setInviteFor(null);
    }
  };

  const inviteCell = (rm) => {
    if (rm.linked) return <span className="text-xs text-emerald-700">Joined</span>;
    const pending = pendingFor(rm.id);
    if (!pending) {
      return (
        <button onClick={() => openInvite(rm)} disabled={loading} className="btn-secondary px-3 py-1 text-xs">
          Invite
        </button>
      );
    }
    return (
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-600" title={`Invite sent to ${pending.email}`}>
          Invited · {pending.email}
        </span>
        {pending.link ? (
          <CopyButton text={pending.link} label="Copy link" />
        ) : (
          <CopyButton text={pending.code} label="Copy code" />
        )}
        <button onClick={() => openInvite(rm)} disabled={loading} className="btn-secondary px-2 py-1 text-xs">
          Resend
        </button>
        <button
          onClick={() => onRevokeInvite(pending.id)}
          disabled={loading}
          className="btn-danger px-2 py-1 text-xs"
        >
          Revoke
        </button>
      </div>
    );
  };

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Joined</th>
            <th>Left</th>
            <th className="text-center">Active</th>
            {canInvite && <th>Invite</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {roommates.map((rm) => (
            <Fragment key={rm.id}>
              <tr>
                <td className="font-medium">
                  {rm.name}
                  {rm.linked && (
                    <span className="ml-2 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-normal text-emerald-700">
                      has login
                      {onUnlink && !readOnly && (
                        <button
                          onClick={() => onUnlink(rm.id)}
                          disabled={loading}
                          className="ml-1 px-1 py-0 text-xs text-emerald-800 underline"
                          title="Detach the login linked to this roommate"
                        >
                          unlink
                        </button>
                      )}
                    </span>
                  )}
                </td>
                <td>
                  <input
                    type="month"
                    value={rm.join_date || ''}
                    disabled={loading || readOnly}
                    onChange={(e) => save(rm, { join_date: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="month"
                    value={rm.leave_date || ''}
                    disabled={loading || readOnly}
                    onChange={(e) => save(rm, { leave_date: e.target.value })}
                  />
                </td>
                <td className="text-center">
                  <input
                    type="checkbox"
                    aria-label={`${rm.name} is active`}
                    checked={rm.is_active}
                    disabled={loading || readOnly}
                    onChange={(e) => save(rm, { is_active: e.target.checked })}
                    className="h-4 w-4"
                  />
                </td>
                {canInvite && <td>{inviteCell(rm)}</td>}
              </tr>
              {canInvite && inviteFor === rm.id && (
                <tr>
                  <td colSpan={columns}>
                    <form onSubmit={sendInvite} className="flex flex-wrap items-center gap-2">
                      <label htmlFor={`invite-email-${rm.id}`} className="text-sm text-slate-600">
                        Invite {rm.name} by email:
                      </label>
                      <input
                        id={`invite-email-${rm.id}`}
                        type="email"
                        required
                        placeholder="flatmate@example.com"
                        value={inviteEmail}
                        onChange={(e) => setInviteEmail(e.target.value)}
                        className="min-w-0 flex-1"
                      />
                      <button
                        type="submit"
                        disabled={sending || !EMAIL_RE.test(inviteEmail.trim())}
                        className="btn-primary"
                      >
                        {sending ? 'Sending…' : 'Send invite'}
                      </button>
                      <button type="button" onClick={() => setInviteFor(null)} className="btn-secondary">
                        Cancel
                      </button>
                    </form>
                  </td>
                </tr>
              )}
              {canInvite && results[rm.id] && (
                <tr>
                  <td colSpan={columns}>
                    <InviteResult
                      invite={results[rm.id]}
                      onClose={() => setResults(({ [rm.id]: _, ...rest }) => rest)}
                    />
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {!readOnly && (
            <tr>
              <td>
                <input
                  placeholder="Roommate name"
                  value={newRoommate.name}
                  disabled={loading}
                  onChange={(e) => setNewRoommate({ ...newRoommate, name: e.target.value })}
                  onKeyDown={(e) => e.key === 'Enter' && addNew()}
                />
              </td>
              <td>
                <input
                  type="month"
                  value={newRoommate.join_date}
                  disabled={loading}
                  onChange={(e) => setNewRoommate({ ...newRoommate, join_date: e.target.value })}
                />
              </td>
              {canInvite ? (
                <td colSpan={2}>
                  <input
                    type="email"
                    aria-label="New roommate's email (optional)"
                    placeholder="Email (optional, sends invite)"
                    value={newRoommate.email}
                    disabled={loading}
                    onChange={(e) => setNewRoommate({ ...newRoommate, email: e.target.value })}
                    onKeyDown={(e) => e.key === 'Enter' && addNew()}
                    className="w-full"
                  />
                </td>
              ) : (
                <td />
              )}
              <td className={canInvite ? '' : 'text-center'}>
                <button
                  onClick={addNew}
                  disabled={
                    loading ||
                    !newRoommate.name.trim() ||
                    (newRoommate.email.trim() !== '' && !EMAIL_RE.test(newRoommate.email.trim()))
                  }
                  className="btn-primary"
                >
                  {newRoommate.email.trim() ? 'Add & invite' : 'Add'}
                </button>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default RoommatesTable;
