// Reusable connection check for the Web3 browser.
// Relaunches the persistent profile, unlocks Phantom if locked, then on a
// benign page (example.org) verifies BOTH injected providers:
//   window.ethereum -> eth_requestAccounts (+ eth_chainId)
//   window.solana   -> connect()
// Prints ONLY the two public addresses, the EVM chain id, and success/failure.
const {
  EXPECTED_EVM,
  EXPECTED_SOL,
  readPassword,
  launch,
  authenticatePage,
  sleep,
  watchApprovals,
  unlockIfNeeded,
} = require('./web3-browser-lib');

async function main() {
  const password = readPassword();
  const browser = await launch();
  const stopWatch = watchApprovals(browser, (m) => console.log('[check]', m), password);
  try {
    const unlocked = await unlockIfNeeded(browser, password, (m) => console.log('[check]', m));
    if (!unlocked) {
      console.log('FAILURE: wallet could not be unlocked');
      process.exitCode = 1;
      return;
    }
    const page = await browser.newPage();
    await authenticatePage(page);
    await page.goto('https://example.org', { waitUntil: 'load', timeout: 60000 });
    const waitProviders = () =>
      page
        .waitForFunction(
          () =>
            !!((window.phantom && window.phantom.ethereum) || window.ethereum) &&
            !!((window.phantom && window.phantom.solana) || window.solana),
          { timeout: 25000 }
        )
        .then(() => true)
        .catch(() => false);
    let hasProviders = await waitProviders();
    if (!hasProviders) {
      // Provider injection is occasionally flaky on first load; reload once.
      await page.reload({ waitUntil: 'load', timeout: 60000 });
      hasProviders = await waitProviders();
    }
    if (!hasProviders) {
      console.log('FAILURE: Phantom providers (window.ethereum / window.solana) did not appear on the page');
      process.exitCode = 1;
      return;
    }
    const result = await page.evaluate(async () => {
      const eth = (window.phantom && window.phantom.ethereum) || window.ethereum;
      const sol = (window.phantom && window.phantom.solana) || window.solana;
      const accounts = await eth.request({ method: 'eth_requestAccounts' });
      const chainId = await eth.request({ method: 'eth_chainId' });
      const resp = await sol.connect();
      return { evm: accounts[0], chainId, sol: resp.publicKey.toString() };
    });
    console.log('EVM address   :', result.evm);
    console.log('EVM chain ID  :', result.chainId);
    console.log('Solana address:', result.sol);
    const ok =
      result.evm.toLowerCase() === EXPECTED_EVM.toLowerCase() && result.sol === EXPECTED_SOL;
    console.log(ok ? 'SUCCESS: both providers connected, addresses match the burner backup' : 'FAILURE: address mismatch');
    if (!ok) process.exitCode = 2;
  } finally {
    stopWatch();
    await browser.close();
  }
}

main()
  .then(() => process.exit(process.exitCode || 0))
  .catch((e) => {
    console.log('FAILURE:', e.message);
    process.exit(1);
  });
