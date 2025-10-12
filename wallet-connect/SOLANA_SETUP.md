# Solana Wallet Integration

This document explains the Solana wallet integration added to the wallet-connect application.

## Overview

The application now supports both **Ethereum** and **Solana** wallets with automatic authentication for both chains.

## Supported Wallets

### Ethereum Wallets
- WalletConnect
- BaseAccount

### Solana Wallets
- **Phantom** - Most popular Solana wallet
- **Solflare** - Feature-rich Solana wallet
- **Torus** - Web-based wallet solution

## Installation

### 1. Install Dependencies

```bash
npm install
```

This will install:
- `@solana/wallet-adapter-base` - Base adapter functionality
- `@solana/wallet-adapter-wallets` - Wallet adapter implementations
- `@solana/web3.js` - Solana JavaScript SDK
- `bs58` - Base58 encoding/decoding
- `tweetnacl` - Cryptographic signatures

### 2. Configure Environment

Update `.env.local`:

```env
# Solana Network (mainnet-beta, devnet, testnet)
VITE_SOLANA_NETWORK=devnet

# Optional: Custom RPC URL
# VITE_SOLANA_RPC_URL=https://api.devnet.solana.com
```

## Architecture

### File Structure

```
src/
├── solana.ts          # Solana wallet configuration and utilities
├── auth.ts            # Updated with multi-chain support
├── main.ts            # Updated UI with Solana wallet connections
└── wagmi.ts           # Ethereum wallet configuration
```

### Key Components

#### 1. `solana.ts` - Solana Wallet Management

**Functions:**
- `connectSolanaWallet(adapter)` - Connect to a Solana wallet
- `disconnectSolanaWallet()` - Disconnect from wallet
- `signSolanaMessage(message)` - Sign a message with Solana wallet
- `getCurrentSolanaAddress()` - Get current wallet address
- `isSolanaWalletConnected()` - Check connection status
- `setupSolanaWalletListeners(adapter, callbacks)` - Set up event listeners

**Configuration:**
- `SOLANA_NETWORK` - Network to connect to (mainnet-beta/devnet/testnet)
- `SOLANA_RPC_URL` - RPC endpoint URL
- `solanaConnection` - Solana RPC connection instance
- `solanaWallets` - Array of available wallet adapters

#### 2. `auth.ts` - Multi-Chain Authentication

**New Types:**
```typescript
export type WalletType = 'ethereum' | 'solana'
```

**New Functions:**
- `signMessageForWalletType(message, address, walletType)` - Sign with appropriate wallet
- `authenticateWalletUniversal(walletAddress, walletType)` - Universal auth flow
- `verifySignature(walletAddress, signature, nonce, walletType)` - Verify with chain type

**Signature Handling:**
- **Ethereum**: Signatures are hex strings (0x...), converted to base64 for backend
- **Solana**: Signatures are already base64, sent directly to backend

#### 3. `main.ts` - Updated UI

**New UI Elements:**
- Separate sections for Ethereum and Solana wallets
- Solana wallet connection buttons (Phantom, Solflare, Torus)
- Account display shows chain type and address

**New Functions:**
- `handleAuthenticationSolana(element, walletAddress)` - Handle Solana auth
- `updateSolanaAccount(element, walletAddress)` - Update Solana account display

## Usage

### Connecting a Solana Wallet

1. User clicks a Solana wallet button (e.g., "Phantom")
2. Wallet extension opens and requests permission
3. User approves connection
4. Application receives wallet address
5. Automatic authentication begins:
   - Request challenge from backend
   - Sign challenge with Solana wallet
   - Verify signature and receive JWT token
6. JWT token is stored in localStorage

### Authentication Flow

```typescript
// 1. User connects Solana wallet
const walletAddress = await connectSolanaWallet(phantomAdapter)

// 2. Automatic authentication
await authenticateWalletUniversal(walletAddress, 'solana')

// 3. JWT token stored
// Ready to make authenticated requests
```

### Making Authenticated Requests

Same as Ethereum - use `authenticatedFetch()`:

```typescript
import { authenticatedFetch } from './auth'

// Create Solana transaction
const response = await authenticatedFetch('/api/solana/transaction', {
  method: 'POST',
  body: JSON.stringify({
    to_address: 'recipient_solana_address',
    amount: 100
  })
})
```

## Signature Verification

### Solana Signature Format

Solana uses **Ed25519** signatures:
- Signing creates a 64-byte signature
- Signatures are base64-encoded for transport
- Backend verifies using the public key (wallet address)

### Backend Requirements

The backend must support Solana signature verification:

```python
# app/mod_common/auth.py

from nacl.signing import VerifyKey
from nacl.encoding import Base64Encoder

def verify_solana_signature(wallet_address: str, signature: str, message: str):
    verify_key = VerifyKey(wallet_address.encode('utf-8'), encoder=Base64Encoder)
    verify_key.verify(message.encode('utf-8'), base64.b64decode(signature))
```

## Development

### Run Development Server

```bash
cd wallet-connect
npm run dev
```

### Build for Production

```bash
npm run build
```

## Troubleshooting

### Wallet Not Detected

**Problem:** Wallet button doesn't work

**Solutions:**
1. Ensure wallet extension is installed (e.g., Phantom)
2. Check browser console for errors
3. Verify wallet is unlocked
4. Try refreshing the page

### Signature Verification Failed

**Problem:** Authentication fails with signature error

**Solutions:**
1. Check wallet address format (should be base58)
2. Verify message is exactly the same on frontend and backend
3. Ensure signature is base64-encoded
4. Check backend logs for specific error

### Network Issues

**Problem:** Can't connect to Solana network

**Solutions:**
1. Check `VITE_SOLANA_NETWORK` in `.env.local`
2. Verify RPC endpoint is accessible
3. Try switching to a different RPC endpoint
4. Use devnet for testing instead of mainnet

## Security Considerations

1. **Signature Verification**: Always verify signatures server-side
2. **Address Validation**: Validate Solana address format (base58)
3. **Network Consistency**: Ensure frontend and backend use same network
4. **RPC Endpoints**: Use reliable RPC providers for production
5. **Token Storage**: JWT tokens are stored in localStorage (consider secure alternatives)

## Testing

### Test with Phantom Wallet (Devnet)

1. Install Phantom browser extension
2. Switch to Devnet in Phantom settings
3. Get devnet SOL from faucet: https://faucet.solana.com
4. Connect wallet in application
5. Sign authentication message
6. Verify JWT token is stored

### Test Authentication Flow

```typescript
// In browser console:
import { isAuthenticated, getAuthToken } from './auth'

console.log('Authenticated:', isAuthenticated())
console.log('Token:', getAuthToken())
```

## Comparison: Ethereum vs Solana

| Feature | Ethereum | Solana |
|---------|----------|---------|
| Address Format | 0x... (hex) | Base58 string |
| Signature Algo | ECDSA | Ed25519 |
| Signature Format | Hex string | Base64 string |
| Popular Wallets | MetaMask, WalletConnect | Phantom, Solflare |
| Network Options | Mainnet, Sepolia, etc. | Mainnet-beta, Devnet, Testnet |

## Resources

- [Solana Wallet Adapter](https://github.com/solana-labs/wallet-adapter)
- [Solana Web3.js Documentation](https://solana-labs.github.io/solana-web3.js/)
- [Phantom Wallet](https://phantom.app/)
- [Solflare Wallet](https://solflare.com/)
- [Solana RPC API](https://docs.solana.com/api)
