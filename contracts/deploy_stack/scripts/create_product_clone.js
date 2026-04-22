require('dotenv').config({ path: '.env.truffle' });

const fs = require('fs');
const path = require('path');
const ProductFactory = artifacts.require('ProductFactory');

function env(name, fallback = '') {
  const v = process.env[name];
  return (v === undefined || v === null || v === '') ? fallback : v;
}

function loadCommitmentsFile(filePath) {
  if (!filePath) return null;
  const full = path.isAbsolute(filePath) ? filePath : path.join(process.cwd(), filePath);
  const raw = JSON.parse(fs.readFileSync(full, 'utf8'));
  const entries = Array.isArray(raw) ? raw : raw.entries;
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error(`PRICE_COMMITMENT_FILE has no entries: ${full}`);
  }
  return entries.map((e) => e.commitment || e.priceCommitment).filter(Boolean);
}

module.exports = async function (callback) {
  const outPath = path.join(process.cwd(), 'output', 'product_clones.json');

  try {
    const factoryAddress = env('PRODUCT_FACTORY_ADDRESS');
    if (!factoryAddress) throw new Error('Missing PRODUCT_FACTORY_ADDRESS in environment');

    const baseName = env('CLONE_BASE_NAME', 'vc-product');
    const singleCommitment = env('PRICE_COMMITMENT', '');
    const fileCommitments = loadCommitmentsFile(env('PRICE_COMMITMENT_FILE', ''));

    let count = Number(env('CLONE_COUNT', '1'));
    const offset = Number(env('PRICE_COMMITMENT_OFFSET', '0'));
    if (!Number.isInteger(offset) || offset < 0) throw new Error('PRICE_COMMITMENT_OFFSET must be >= 0');
    if (!Number.isInteger(count) || count <= 0) throw new Error('CLONE_COUNT must be a positive integer');

    if (fileCommitments) {
      if (offset + count > fileCommitments.length) {
        throw new Error(`CLONE_COUNT  with OFFSET  exceeds PRICE_COMMITMENT_FILE size `);
      }
    }

    const accounts = await web3.eth.getAccounts();
    const sender = accounts[0];

    const factory = await ProductFactory.at(factoryAddress);
    const bondAmount = await factory.bondAmount();
    if (bondAmount.toString() === '0') throw new Error('Factory bondAmount is 0; cannot create products');

    const startBalanceWei = await web3.eth.getBalance(sender);
    console.log(JSON.stringify({ sender, factoryAddress, requestedClones: count, offset, bondAmountWei: bondAmount.toString(), senderBalanceWei: startBalanceWei.toString() }));

    let existing = [];
    if (fs.existsSync(outPath)) {
      try {
        existing = JSON.parse(fs.readFileSync(outPath, 'utf8'));
        if (!Array.isArray(existing)) existing = [];
      } catch (_) {
        existing = [];
      }
    }

    const created = [];

    for (let i = 0; i < count; i++) {
      const name = `${baseName}-${Date.now()}-${i + 1}`;
      const commitment = fileCommitments
        ? String(fileCommitments[offset + i])
        : (singleCommitment || web3.utils.soliditySha3(
            { type: 'string', value: `${name}:price` },
            { type: 'address', value: sender },
            { type: 'uint256', value: Date.now() + i }
          ));

      try {
        const tx = await factory.createProduct(name, commitment, { from: sender, value: bondAmount.toString() });
        const evt = tx.logs.find((l) => l.event === 'ProductCreated');
        const productAddress = evt?.args?.product;
        const productId = evt?.args?.productId?.toString?.() || null;
        if (!productAddress) throw new Error('ProductCreated event missing product address');

        const row = {
          productAddress,
          productId,
          priceCommitment: commitment,
          txHash: tx.tx,
          productName: name,
          bondAmountWei: bondAmount.toString(),
        };

        created.push(row);
        existing.push(row);
        fs.writeFileSync(outPath, JSON.stringify(existing, null, 2));
        console.log(JSON.stringify({ created: i + 1, ...row }));
      } catch (err) {
        const currentBalanceWei = await web3.eth.getBalance(sender);
        console.error(JSON.stringify({ failedAtIndex: i + 1, createdSoFar: created.length, sender, senderBalanceWei: currentBalanceWei.toString(), reason: err?.message || String(err) }));
        throw err;
      }
    }

    callback();
  } catch (err) {
    callback(err);
  }
};
