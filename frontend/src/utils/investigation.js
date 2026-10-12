export function classifyTransaction(tx) {
  if (tx.value_wei != null && /^\d+$/.test(String(tx.value_wei))) {
    if (BigInt(String(tx.value_wei)) === 0n) return { label: 'Zero native ETH', hint: 'May be a contract interaction; token transfers are not decoded', tone: 'text-violet-300 bg-violet-400/10 border-violet-400/20' };
    return { label: 'ETH value', hint: 'Native ETH transferred', tone: 'text-cyan-300 bg-cyan-400/10 border-cyan-400/20' };
  }
  return { label: 'Value unknown', hint: 'Native ETH value not available', tone: 'text-slate-300 bg-slate-400/10 border-slate-400/20' };
}

export function downloadTransactions(transactions) {
  const columns = ['hash', 'from_address', 'to_address', 'block_number', 'value_wei', 'risk_score', 'risk_factors'];
  const escape = value => '"' + String(value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : value).replace(/"/g, '""') + '"';
  const csv = [columns.join(','), ...transactions.map(tx => columns.map(col => escape(tx[col])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'chainscope-transactions.csv';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
