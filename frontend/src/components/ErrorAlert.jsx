function ErrorAlert({ message, onRetry }) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-rose-700">
      <p className="font-medium">Error</p>
      <p className="mt-1 text-sm">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="btn-secondary mt-3 text-xs">
          Retry
        </button>
      )}
    </div>
  );
}

export default ErrorAlert;
