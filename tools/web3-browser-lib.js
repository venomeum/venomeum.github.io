// Shared helpers for the Web3 browser (Phantom, multichain EVM + Solana).
// SECURITY: this module never prints the mnemonic or the wallet password.
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

const ROOT = __dirname;
const EXT_ID = 'bfnaelmomeimhlpmgjnjophhpkkoljpa'; // official Phantom extension id
const EXT_PATH = path.join(ROOT, 'phantom');
const PROFILE_DIR = path.join(ROOT, 'profile');
const PASSWORD_FILE = path.join(ROOT, '.wallet-password');
const BACKUP_FILE = '/home/hatch/workspace/your_files/venomeum-burner-wallet-backup.json';

const EXPECTED_EVM = '0x09045763Ea68FB7Ef0E0e51C26bcCf45846077f1';
const EXPECTED_SOL = 'AjyRpt4jQ8WkS21J2HreLYHJf72wAWrAiJPWjP2N23Tz';

function readPassword() {
  return fs.readFileSync(PASSWORD_FILE, 'utf8').trim();
}

function readMnemonic() {
  const backup = JSON.parse(fs.readFileSync(BACKUP_FILE, 'utf8'));
  return backup.mnemonic;
}

// This VM reaches the internet only through an authenticated egress proxy
// (env vars). Chromium cannot do proxy basic-auth from --proxy-server, so we
// run a tiny local CONNECT forwarder on 127.0.0.1:18080 that injects the
// Proxy-Authorization header upstream, and point Chromium at it (no auth).
const net = require('net');
const http = require('http');

const LOCAL_PROXY_PORT = 18080;
let localProxyStarted = false;

function proxyConfig() {
  const raw =
    process.env.https_proxy || process.env.HTTPS_PROXY || process.env.http_proxy || '';
  if (!raw) return null;
  try {
    const u = new URL(raw);
    return {
      host: u.hostname,
      port: Number(u.port || 3128),
      auth:
        'Basic ' +
        Buffer.from(
          `${decodeURIComponent(u.username || '')}:${decodeURIComponent(u.password || '')}`
        ).toString('base64'),
    };
  } catch (_) {
    return null;
  }
}

function startLocalProxy(up) {
  if (localProxyStarted) return;
  localProxyStarted = true;
  const server = net.createServer((client) => {
    client.once('data', (chunk) => {
      const text = chunk.toString('latin1');
      const firstLine = text.slice(0, text.indexOf('\r\n'));
      if (firstLine.startsWith('CONNECT ')) {
        const target = firstLine.split(' ')[1];
        const upstream = net.connect(up.port, up.host, () => {
          upstream.write(
            `CONNECT ${target} HTTP/1.1\r\nHost: ${target}\r\nProxy-Authorization: ${up.auth}\r\nProxy-Connection: Keep-Alive\r\n\r\n`
          );
        });
        let buf = Buffer.alloc(0);
        const onData = (c) => {
          buf = Buffer.concat([buf, c]);
          const idx = buf.indexOf('\r\n\r\n');
          if (idx === -1) return;
          upstream.removeListener('data', onData);
          const statusLine = buf.slice(0, buf.indexOf('\r\n')).toString('latin1');
          const rest = buf.slice(idx + 4);
          if (/ 200 /.test(statusLine)) {
            client.write('HTTP/1.1 200 Connection Established\r\n\r\n');
            if (rest.length) client.write(rest);
            upstream.pipe(client);
            client.pipe(upstream);
          } else {
            client.write('HTTP/1.1 502 Bad Gateway\r\n\r\n');
            client.destroy();
            upstream.destroy();
          }
        };
        upstream.on('data', onData);
        upstream.on('error', () => client.destroy());
        client.on('error', () => upstream.destroy());
      } else {
        // Plain-HTTP proxy request: inject the auth header into the raw
        // request head and stream everything through.
        const headersEnd = text.indexOf('\r\n\r\n');
        let rawHead = text.slice(0, headersEnd);
        if (!/proxy-authorization:/i.test(rawHead)) {
          rawHead += `\r\nProxy-Authorization: ${up.auth}`;
        }
        const rest = chunk.slice(headersEnd + 4);
        const upstream = net.connect(up.port, up.host, () => {
          upstream.write(rawHead + '\r\n\r\n');
          if (rest.length) upstream.write(rest);
          client.pipe(upstream);
          upstream.pipe(client);
        });
        upstream.on('error', () => client.destroy());
        client.on('error', () => upstream.destroy());
      }
    });
    client.on('error', () => {});
  });
  server.on('error', () => {});
  server.listen(LOCAL_PROXY_PORT, '127.0.0.1');
  server.unref(); // never keep the process alive just for the proxy
}

async function launch() {
  const proxy = proxyConfig();
  const args = [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--ignore-certificate-errors',
    `--disable-extensions-except=${EXT_PATH}`,
    `--load-extension=${EXT_PATH}`,
  ];
  if (proxy) {
    startLocalProxy(proxy);
    await sleep(300);
    args.push(`--proxy-server=http://127.0.0.1:${LOCAL_PROXY_PORT}`);
  }
  const browser = await puppeteer.launch({
    headless: false, // run under xvfb-run; extensions need a headed-capable build
    ignoreHTTPSErrors: true, // the VM's egress proxy MITMs TLS with a local CA
    userDataDir: PROFILE_DIR,
    defaultViewport: { width: 1280, height: 900 },
    timeout: 90000,
    protocolTimeout: 120000,
    args,
  });
  return browser;
}

// Kept for API compatibility: proxy auth is now handled by the local
// forwarder (see startLocalProxy), so pages need no per-page authentication.
async function authenticatePage(_page) {}

// Click a visible button/link whose text matches one of `texts` (case-insensitive,
// exact match preferred, then substring). Returns true if something was clicked.
async function clickByText(page, texts) {
  const wanted = texts.map((t) => t.toLowerCase());
  return page.evaluate((wanted) => {
    const els = Array.from(
      document.querySelectorAll('button, a, [role="button"], div[tabindex], span')
    ).filter((el) => {
      const r = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    });
    const norm = (s) => (s || '').trim().toLowerCase().replace(/\s+/g, ' ');
    let target = els.find((el) => wanted.includes(norm(el.innerText || el.textContent)));
    if (!target) {
      target = els.find((el) => {
        const t = norm(el.innerText || el.textContent);
        return t && wanted.some((w) => t.includes(w)) && t.length < 80;
      });
    }
    if (target) {
      target.click();
      return true;
    }
    return false;
  }, wanted);
}

// Short debug snapshot of what is on screen: headings + button labels only.
// Never includes input values.
async function describeScreen(page) {
  return page.evaluate(() => {
    const vis = (el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'))
      .filter(vis)
      .map((el) => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' '))
      .filter(Boolean);
    const headings = Array.from(document.querySelectorAll('h1,h2,h3,p'))
      .filter(vis)
      .map((el) => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' '))
      .filter(Boolean)
      .slice(0, 8);
    const inputs = Array.from(document.querySelectorAll('input, textarea')).filter(vis).length;
    return { url: location.href, headings, buttons: [...new Set(buttons)].slice(0, 20), inputs };
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Click a button by visible text using a TRUSTED CDP mouse click on the
// element handle. Phantom's sensitive screens (unlock, connect) ignore
// untrusted el.click() events, so this is required there.
async function trustedClickByText(page, texts) {
  const wanted = texts.map((t) => t.toLowerCase());
  const buttons = await page.$$('button');
  for (const b of buttons) {
    const label = await b
      .evaluate((el) => (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' '))
      .catch(() => '');
    if (!label) continue;
    const lower = label.toLowerCase();
    if (wanted.some((w) => lower === w || lower.startsWith(w))) {
      await b.click().catch(() => {});
      return label;
    }
  }
  return null;
}

// Wake the extension's service worker by briefly opening its popup page.
// The page renders blank in a tab, but opening it starts the background
// logic; without this, dapp provider injection is unreliable.
async function wakeExtension(browser) {
  try {
    const wake = await browser.newPage();
    await wake
      .goto(`chrome-extension://${EXT_ID}/popup.html`, { waitUntil: 'load', timeout: 30000 })
      .catch(() => {});
    await sleep(3500);
    await wake.close().catch(() => {});
  } catch (_) {}
}

// Poll all open pages for Phantom notification windows and handle them:
//  - visible empty password field  -> trusted-type the stored password and
//    press Enter (Phantom unlocks on Enter; the Unlock button ignores
//    untrusted clicks, and even trusted clicks proved unreliable).
//  - Connect / Approve / Confirm button -> trusted click.
// Returns a stop function. Logs actions only — never secret values.
function watchApprovals(browser, log, password) {
  const unlockTries = new Map(); // page -> count
  let stopped = false;
  (async () => {
    while (!stopped) {
      try {
        const pages = await browser.pages();
        for (const p of pages) {
          const url = p.url();
          if (!url.includes(EXT_ID) || !url.includes('notification')) continue;
          try {
            const pwState = await p
              .evaluate(() => {
                const els = Array.from(document.querySelectorAll('input[type="password"]'));
                const vis = els.find((el) => el.getBoundingClientRect().width > 0);
                return vis ? { present: true, len: (vis.value || '').length } : { present: false, len: 0 };
              })
              .catch(() => ({ present: false, len: 0 }));
            if (pwState.present && password) {
              const tries = unlockTries.get(p) || 0;
              if (pwState.len === 0 && tries < 3) {
                unlockTries.set(p, tries + 1);
                const pw = await p.$('input[type="password"]');
                if (pw) {
                  await pw.click().catch(() => {});
                  await p.keyboard.type(password, { delay: 15 });
                  await p.keyboard.press('Enter');
                  if (log) log('notification: password entered, unlock submitted');
                }
              }
              continue; // wait for the unlock to take effect
            }
            const clicked = await trustedClickByText(p, ['Connect', 'Approve', 'Confirm']);
            if (clicked && log) log(`notification: clicked "${clicked}"`);
          } catch (_) {}
        }
      } catch (_) {}
      await sleep(900);
    }
  })();
  return () => {
    stopped = true;
  };
}

// Phantom's popup renders blank when opened as a tab, so lock state can't be
// probed there. In practice the wallet asks for its password inside the
// connection notification window, which watchApprovals handles. This helper
// just wakes the extension and reports ready-to-proceed.
async function unlockIfNeeded(browser, password, log) {
  await wakeExtension(browser);
  if (log) log('extension awake; any unlock prompt is handled in the notification window');
  return true;
}

module.exports = {
  EXT_ID,
  EXPECTED_EVM,
  EXPECTED_SOL,
  readPassword,
  readMnemonic,
  launch,
  authenticatePage,
  clickByText,
  trustedClickByText,
  describeScreen,
  sleep,
  watchApprovals,
  unlockIfNeeded,
  wakeExtension,
};
