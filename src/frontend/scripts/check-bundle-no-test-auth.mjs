// Fails if a built frontend contains anything from the test-only E2E auth stand-in.
// Run after `next build` with production settings: npm run check:bundle
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const root = '.next';
const markers = ['auth-stub', 'E2E auth stand-in', 'KOROFARM_E2E_AUTH_STANDIN', 'e2e-test-key', 'seed_e2e', '127.0.0.1:54999'];
const hits = [];
let scanned = 0;
function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (name === 'cache' || name === 'dev') continue;  // build cache and dev-server output are not shipped
    if (statSync(path).isDirectory()) { walk(path); continue; }
    if (!/\.(js|mjs|cjs|html|json|txt|rsc)$/.test(name)) continue;
    scanned += 1;
    const text = readFileSync(path, 'utf8');
    for (const marker of markers) if (text.includes(marker)) hits.push(`${path}: ${marker}`);
  }
}
walk(root);
if (scanned === 0) { console.error('No build output found in .next; run next build first.'); process.exit(2); }
if (hits.length) { console.error(`Test-only auth material found in the build:\n${hits.join('\n')}`); process.exit(1); }
console.log(`OK: ${scanned} build files scanned, no test-only auth material.`);
