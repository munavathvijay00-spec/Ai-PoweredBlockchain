import { useEffect, useMemo, useRef, useState } from 'react';

const norm = value => (value || '').toLowerCase();
const short = value => value ? `${value.slice(0, 7)}…${value.slice(-5)}` : '—';
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const COLORS = {
  root: '#22d3ee',
  high: '#fb7185',
