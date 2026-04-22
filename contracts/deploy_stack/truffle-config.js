require('dotenv').config({ path: '.env.truffle' });
const HDWalletProvider = require('@truffle/hdwallet-provider');

const {
  PRIVATE_KEY,
  MNEMONIC,
  SEPOLIA_RPC_URL,
  SEPOLIA_RPC_URLS,
} = process.env;

const makeProvider = () => {
  const rpcCandidates = (SEPOLIA_RPC_URLS || '')
    .split(',')
    .map((u) => u.trim())
    .filter(Boolean);

  if (SEPOLIA_RPC_URL) rpcCandidates.unshift(SEPOLIA_RPC_URL);

  if (rpcCandidates.length === 0) {
    throw new Error('Set SEPOLIA_RPC_URL (or SEPOLIA_RPC_URLS) in .env.truffle');
  }

  const rpcUrl = rpcCandidates[0];

  if (PRIVATE_KEY) {
    return new HDWalletProvider({
      privateKeys: [PRIVATE_KEY],
      providerOrUrl: rpcUrl,
      chainId: 11155111,
      pollingInterval: 20000,
    });
  }

  if (MNEMONIC) {
    return new HDWalletProvider({
      mnemonic: { phrase: MNEMONIC },
      providerOrUrl: rpcUrl,
      addressIndex: 0,
      numberOfAddresses: 1,
      derivationPath: "m/44'/60'/0'/0/",
      chainId: 11155111,
      pollingInterval: 20000,
    });
  }

  throw new Error('Set PRIVATE_KEY or MNEMONIC in .env.truffle');
};

module.exports = {
  contracts_directory: './contracts',
  contracts_build_directory: './build/contracts',
  migrations_directory: './migrations',
  networks: {
    sepolia: {
      provider: () => makeProvider(),
      network_id: 11155111,
      confirmations: 2,
      timeoutBlocks: 2000,
      networkCheckTimeout: 600000,
      skipDryRun: true,
    },
  },
  compilers: {
    solc: {
      version: '0.8.21',
      settings: {
        optimizer: { enabled: true, runs: 200 },
        evmVersion: 'shanghai',
      },
    },
  },
};
