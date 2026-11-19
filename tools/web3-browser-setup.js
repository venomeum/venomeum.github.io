// One-time setup: launch the persistent Web3 browser, import the burner
// wallet's recovery phrase into Phantom, set the stored password, and verify
// that BOTH derived addresses (EVM + Solana) match the backup exactly.
//
// The onboarding is driven as a state machine: each round inspects the
// current screen and takes the matching action, so the script also copes
// with a resumed/partial onboarding state.
//
// SECURITY: the mnemonic is read in-memory from the backup JSON and typed
// directly into the extension page. It is never printed, logged, screenshotted,
// or written anywhere else.
const {
  EXT_ID,
  EXPECTED_EVM,
  EXPECTED_SOL,
  readPassword,
  readMnemonic,
  launch,
  authenticatePage,
  clickByText,
  describeScreen,
  sleep,
  watchApprovals,
  wakeExtension,
} = require('./web3-browser-lib');

function log(...args) {
  console.log('[setup]', ...args);
}

async function countFilled(page) {
  return page.evaluate(() => {
    const vis = (el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const fields = Array.from(
      document.querySelectorAll(
        'input:not([type="password"]):not([type="checkbox"]):not([type="hidden"]), textarea, [contenteditable="true"]'
      )
    ).filter(vis);
    return fields.filter((el) => ((el.value || el.innerText || '').trim().length > 0)).length;
  });
}

async function fillPhrase(page, phrase) {
  const words = phrase.trim().split(/\s+/);
  const fieldCount = await page.evaluate(() => {
    const vis = (el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    return Array.from(
      document.querySelectorAll(
        'input:not([type="password"]):not([type="checkbox"]):not([type="hidden"]), textarea, [contenteditable="true"]'
      )
    ).filter(vis).length;
  });
  log(`phrase screen: ${fieldCount} entry field(s), ${words.length} words to enter`);
  if (fieldCount === 0) throw new Error('No phrase entry fields found');

  if (fieldCount === 1) {
    const el = await page.$(
      'textarea, input:not([type="password"]):not([type="checkbox"]):not([type="hidden"]), [contenteditable="true"]'
    );
    await el.click();
    await el.type(phrase);
    return;
  }
  // Grid of word fields: type the whole phrase into field #1 (Phantom splits
  // on spaces), verify, and fall back to per-word entry if needed.
  const handles = await page.$$(
    'input:not([type="password"]):not([type="checkbox"]):not([type="hidden"]), textarea'
  );
  await handles[0].click();
  await handles[0].type(phrase);
  await sleep(600);
  let filled = await countFilled(page);
  log(`after whole-phrase type: ${filled} field(s) filled`);
  if (filled < words.length) {
    const fields = await page.$$(
      'input:not([type="password"]):not([type="checkbox"]):not([type="hidden"]), textarea'
    );
    for (let i = 0; i < Math.min(fields.length, words.length); i++) {
      const val = await fields[i].evaluate((el) => el.value || '');
      if (!val) {
        await fields[i].click();
        await fields[i].type(words[i]);
      }
    }
    filled = await countFilled(page);
    log(`after per-word fill: ${filled} field(s) filled`);
  }
  if (filled < words.length) {
    throw new Error(`Only ${filled}/${words.length} phrase fields filled`);
  }
}

// Handle the "Create a password" screen robustly: re-query field handles
// between interactions (React re-renders invalidate them), verify only
// lengths/equality/checked/disabled booleans (never values), and click
// Continue only once it is enabled.
async function completePasswordScreen(page, password) {
  const state = await page.evaluate(() => {
    const pw = Array.from(document.querySelectorAll('input[type="password"]'));
    const cb = document.querySelector('input[type="checkbox"]');
    const cont = Array.from(document.querySelectorAll('button')).find(
      (b) => (b.innerText || '').trim().toLowerCase() === 'continue'
    );
    return {
      pwCount: pw.length,
      pwLens: pw.map((el) => (el.value || '').length),
      pwEqual: pw.length >= 2 ? pw[0].value === pw[1].value : null,
      hasCheckbox: !!cb,
      checked: cb ? cb.checked : null,
      continueDisabled: cont ? cont.disabled : null,
    };
  });
  log('password screen state:', JSON.stringify(state));

  // Fill any empty password field, re-querying handles each time.
  for (let i = 0; i < state.pwCount; i++) {
    if (state.pwLens[i] > 0) continue;
    const inputs = await page.$$('input[type="password"]');
    if (inputs[i]) {
      await inputs[i].click();
      await inputs[i].type(password, { delay: 5 });
    }
  }
  await sleep(400);
  // Ensure the terms checkbox is checked; fall back to clicking its label.
  const cbState = await page.evaluate(() => {
    const cb = document.querySelector('input[type="checkbox"]');
    if (!cb) return 'none';
    if (!cb.checked) cb.click();
    return cb.checked ? 'checked' : 'still-unchecked';
  });
  if (cbState === 'still-unchecked') {
    await page.evaluate(() => {
      const els = Array.from(document.querySelectorAll('label, div, span'));
      const t = els.find(
        (el) => /i agree to the terms/i.test(el.innerText || '') && el.getBoundingClientRect().width > 0
      );
      if (t) t.click();
    });
    await sleep(300);
  }
  const after = await page.evaluate(() => {
    const pw = Array.from(document.querySelectorAll('input[type="password"]'));
    const cb = document.querySelector('input[type="checkbox"]');
    const cont = Array.from(document.querySelectorAll('button')).find(
      (b) => (b.innerText || '').trim().toLowerCase() === 'continue'
    );
    return {
      pwLens: pw.map((el) => (el.value || '').length),
      pwEqual: pw.length >= 2 ? pw[0].value === pw[1].value && pw[0].value.length > 0 : null,
      checked: cb ? cb.checked : null,
      continueDisabled: cont ? cont.disabled : null,
    };
  });
  log('password screen after fill:', JSON.stringify(after));
  if (after.continueDisabled === false) {
    await clickByText(page, ['Continue']);
    await sleep(3000);
    return true;
  }
  return false;
}

async function runOnboarding(page, phrase, password) {
  let phraseDone = false;
  let idleRounds = 0;
  for (let round = 0; round < 16; round++) {
    let screen;
    try {
      screen = await describeScreen(page);
    } catch (e) {
      // Onboarding tab closed/navigated away (e.g. after "Get Started") —
      // that means onboarding is done; verification happens on a fresh page.
      log(`round ${round}: onboarding page gone (${e.message}); treating as complete`);
      return;
    }
    log(`round ${round}:`, JSON.stringify(screen));
    const buttons = screen.buttons.map((b) => b.toLowerCase());
    const hasBtn = (t) => buttons.some((b) => b === t || b.startsWith(t));

    const pwCount = await page.evaluate(
      () => document.querySelectorAll('input[type="password"]').length
    );
    if (pwCount > 0) {
      await completePasswordScreen(page, password);
      idleRounds = 0;
      await sleep(1500);
      continue;
    }

    if (hasBtn('i already have a wallet')) {
      await clickByText(page, ['I Already Have a Wallet']);
      idleRounds = 0;
      await sleep(2500);
      continue;
    }
    if (buttons.some((b) => b.startsWith('import recovery phrase'))) {
      await clickByText(page, ['Import Recovery Phrase']);
      idleRounds = 0;
      await sleep(2500);
      continue;
    }
    if (!phraseDone && screen.inputs > 0) {
      await clickByText(page, ['I have a 24-word recovery phrase']);
      await sleep(1200);
      await fillPhrase(page, phrase);
      phraseDone = true;
      await sleep(500);
      await clickByText(page, ['Import Wallet', 'Continue', 'Import', 'Next']);
      idleRounds = 0;
      await sleep(3000);
      continue;
    }
    const affirmatives = [
      'Continue',
      'Get Started',
      'Done',
      'Finish',
      'Skip',
      'No Thanks',
      'Not Now',
      'Start Using Phantom',
      'Next',
    ];
    const clicked = await clickByText(page, affirmatives);
    if (clicked) {
      idleRounds = 0;
      await sleep(2500);
      continue;
    }
    idleRounds++;
    log(`round ${round}: nothing actionable (idle ${idleRounds})`);
    if (idleRounds >= 2) break;
    await sleep(2000);
  }
}

// Open the benign test page and wait for both Phantom providers to inject
// (one reload retry — injection is occasionally flaky on first load).
async function openTestPage(browser) {
  const page = await browser.newPage();
  await authenticatePage(page);
  await page.goto('https://example.org', { waitUntil: 'load', timeout: 60000 });
  const waitProviders = () =>
    page
      .waitForFunction(
        () =>
          !!((window.phantom && window.phantom.ethereum) || window.ethereum) &&
          !!((window.phantom && window.phantom.solana) || window.solana),
        { timeout: 20000 }
      )
      .then(() => true)
      .catch(() => false);
  let ok = await waitProviders();
  if (!ok) {
    await page.reload({ waitUntil: 'load', timeout: 60000 });
    ok = await waitProviders();
  }
  return { page, providersReady: ok };
}

// Non-interactive probe: if this profile already holds the wallet and
// example.org is a trusted site, the addresses come back without any prompt.
// Returns { evmAddr, solAddress } (either may be null).
async function probeExisting(browser) {
  await wakeExtension(browser);
  const { page, providersReady } = await openTestPage(browser);
  try {
    if (!providersReady) return { evmAddr: null, solAddress: null };
    return await page.evaluate(async () => {
      const out = { evmAddr: null, solAddress: null };
      const eth = (window.phantom && window.phantom.ethereum) || window.ethereum;
      const sol = (window.phantom && window.phantom.solana) || window.solana;
      if (eth) {
        const accs = await eth.request({ method: 'eth_accounts' });
        out.evmAddr = (accs && accs[0]) || null;
      }
      if (sol) {
        try {
          const resp = await sol.connect({ onlyIfTrusted: true });
          out.solAddress = resp.publicKey.toString();
        } catch (_) {}
      }
      return out;
    });
  } finally {
    await page.close().catch(() => {});
  }
}

// Interactive verification: full connect via both providers (the approval
// watcher handles unlock + connect prompts). Returns the result object.
async function verifyViaProviders(browser) {
  const { page, providersReady } = await openTestPage(browser);
  try {
    if (!providersReady) return { hasEthereum: false, hasSolana: false };
    return await page.evaluate(async () => {
      const out = {};
      const eth = (window.phantom && window.phantom.ethereum) || window.ethereum;
      const sol = (window.phantom && window.phantom.solana) || window.solana;
      out.hasEthereum = !!eth;
      out.hasSolana = !!sol;
      if (eth) {
        out.ethAccounts = await eth.request({ method: 'eth_requestAccounts' });
        out.chainId = await eth.request({ method: 'eth_chainId' });
      }
      if (sol) {
        const resp = await sol.connect();
        out.solAddress = resp.publicKey.toString();
      }
      return out;
    });
  } finally {
    await page.close().catch(() => {});
  }
}

function reportAndJudge(evmAddr, solAddress, chainId) {
  const evmOk = !!evmAddr && evmAddr.toLowerCase() === EXPECTED_EVM.toLowerCase();
  const solOk = solAddress === EXPECTED_SOL;
  console.log('EVM address   :', evmAddr || '(none)', '| match:', evmOk);
  console.log('Solana address:', solAddress || '(none)', '| match:', solOk);
  if (chainId) console.log('Chain ID      :', chainId);
  return evmOk && solOk;
}

async function main() {
  const password = readPassword();
  const phrase = readMnemonic();
  const browser = await launch();
  const stopWatch = watchApprovals(browser, log, password);
  try {
    // Idempotency: if the persistent profile already holds this wallet,
    // skip the import entirely.
    const existing = await probeExisting(browser);
    if (existing.evmAddr || existing.solAddress) {
      log('profile already has a wallet connected for the test page');
      if (reportAndJudge(existing.evmAddr, existing.solAddress, null)) {
        console.log('SETUP SUCCESS: wallet already present; both addresses verified.');
        return;
      }
      console.error('ADDRESS MISMATCH — stopping as instructed. Do not use these accounts.');
      process.exitCode = 2;
      return;
    }

    const page = await browser.newPage();
    await page.goto(`chrome-extension://${EXT_ID}/onboarding.html`, {
      waitUntil: 'load',
      timeout: 60000,
    });
    await sleep(4000);
    try {
      await runOnboarding(page, phrase, password);
    } catch (e) {
      if (/detached frame/i.test(e.message)) {
        log('onboarding page detached mid-flow; continuing to verification');
      } else {
        throw e;
      }
    }
    try {
      log('onboarding finished; final screen:', JSON.stringify(await describeScreen(page)));
    } catch (_) {
      log('onboarding page closed (expected after completion)');
    }
    await page.close().catch(() => {});

    // Verify both addresses through the injected providers on a benign page
    // (this is also a first connection test).
    const result = await verifyViaProviders(browser);
    log('provider test:', JSON.stringify(result));
    const evmAddr = result.ethAccounts && result.ethAccounts[0];
    if (!reportAndJudge(evmAddr, result.solAddress, result.chainId)) {
      console.error('ADDRESS MISMATCH — stopping as instructed. Do not use these accounts.');
      process.exitCode = 2;
      return;
    }
    console.log('SETUP SUCCESS: both addresses verified against the backup.');
  } finally {
    stopWatch();
    await browser.close();
  }
}

main()
  .then(() => process.exit(process.exitCode || 0))
  .catch((e) => {
    console.error('[setup] FAILED:', e.message);
    process.exit(1);
  });
