import { useState } from 'react';
import App from './App.jsx';
import CaseWorkspace from './components/CaseWorkspace.jsx';
import { api } from './api/client';

const VALID = /^0x[a-fA-F0-9]{40}$/;
const short = value => value ? `${value.slice(0, 9)}…${value.slice(-6)}` : '—';
const eth = wei => {
  try { return (Number(BigInt(String(wei || '0'))) / 1e18).toLocaleString(undefined, { maximumFractionDigits: 6 }); }
  catch { return '—'; }
};
