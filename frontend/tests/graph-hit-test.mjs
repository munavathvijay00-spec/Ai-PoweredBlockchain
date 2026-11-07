import assert from 'node:assert/strict';
import { nearestEdgeAt } from '../src/utils/graphHitTest.js';

const points = [{ id: 'root', x: 0, y: 0 }, { id: 'peer', x: 100, y: 0 }, { id: 'other', x: 100, y: 100 }];
const edges = [{ id: 'out', from: 'root', to: 'peer' }, { id: 'next', from: 'peer', to: 'other' }];
assert.equal(nearestEdgeAt(points, edges, 52, 5)?.id, 'out');
assert.equal(nearestEdgeAt(points, edges, 102, 65)?.id, 'next');
assert.equal(nearestEdgeAt(points, edges, 50, 30), null);
assert.equal(nearestEdgeAt(points, [{ from: 'missing', to: 'peer' }], 50, 0), null);
assert.equal(nearestEdgeAt(points, [{ from: 'root', to: 'root' }], 0, 0), null);
console.log('Graph edge hit-test checks passed.');
