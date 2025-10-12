# Wallet Connect with Authentication

Frontend application for connecting Web3 wallets and authenticating with the MYKOBO DAPP backend.

## Features

- **Wallet Connection**: Connect using WalletConnect or BaseAccount
- **Automatic Authentication**: Automatically authenticates with backend after wallet connection
- **JWT Token Management**: Stores and manages authentication tokens
- **Signature-based Auth**: Uses wallet signatures for secure authentication

## Setup

### 1. Install Dependencies

```bash
npm install
```

### 2. Configure Environment

Update `.env.local` with your settings:

```env
VITE_WC_PROJECT_ID=your_walletconnect_project_id
VITE_API_BASE_URL=http://localhost:8000
```

### 3. Run Development Server

```bash
npm run dev
```

## Authentication Flow

When a user connects their wallet, the following happens automatically:

### 1. Wallet Connection
User clicks a connector button (WalletConnect, BaseAccount, etc.)

### 2. Request Challenge
```typescript
// Frontend requests a challenge from backend
POST /auth/auth/challenge
{
  "wallet_address": "0x..."
}

// Backend responds with:
{
  "challenge": {
    "nonce": "unique_nonce",
    "message": "Sign this message to authenticate...",
    "timestamp": 1234567890
  },
  "expires_in": 300
}
```

### 3. Sign Message
```typescript
// User signs the challenge message with their wallet
const signature = await signMessage(config, {
  message: challenge.message,
  account: walletAddress
})
```

### 4. Verify Signature
```typescript
// Frontend sends signature to backend for verification
POST /auth/auth/verify
{
  "wallet_address": "0x...",
  "signature": "base64_signature",
  "nonce": "unique_nonce"
}

// Backend responds with JWT token:
{
  "token": "eyJhbGc...",
  "wallet_address": "0x...",
  "expires_in": 86400
}
```

### 5. Store Token
The JWT token is stored in `localStorage` and automatically included in all authenticated API requests.

## Usage

### Auth Module (`src/auth.ts`)

#### Complete Authentication Flow
```typescript
import { authenticateWallet } from './auth'

// Authenticate wallet after connection
const token = await authenticateWallet(walletAddress)
console.log('Authenticated with token:', token)
```

#### Manual Flow
```typescript
import {
  requestChallenge,
  signAuthMessage,
  verifySignature
} from './auth'

// 1. Request challenge
const challenge = await requestChallenge(walletAddress)

// 2. Sign challenge
const signature = await signAuthMessage(challenge.message, walletAddress)

// 3. Verify and get token
const { token } = await verifySignature(walletAddress, signature, challenge.nonce)
```

#### Making Authenticated Requests
```typescript
import { authenticatedFetch } from './auth'

// Make authenticated API call
const response = await authenticatedFetch('/api/solana/transaction', {
  method: 'POST',
  body: JSON.stringify({
    to_address: 'recipient_address',
    amount: 100
  })
})

const data = await response.json()
```

#### Check Authentication Status
```typescript
import { isAuthenticated, getAuthToken } from './auth'

if (isAuthenticated()) {
  const token = getAuthToken()
  console.log('User is authenticated')
}
```

#### Logout
```typescript
import { logout } from './auth'

// Clear authentication token
logout()
```

## Architecture

### Files

- **`src/auth.ts`**: Authentication module with all auth functions
- **`src/main.ts`**: Main application with wallet connection and auth integration
- **`src/wagmi.ts`**: Wagmi configuration for wallet connectors

### Key Functions

| Function | Description |
|----------|-------------|
| `authenticateWallet()` | Complete auth flow (challenge → sign → verify) |
| `requestChallenge()` | Request challenge from backend |
| `signAuthMessage()` | Sign message with wallet |
| `verifySignature()` | Verify signature and get JWT |
| `authenticatedFetch()` | Make authenticated API requests |
| `isAuthenticated()` | Check if user has valid token |
| `logout()` | Clear authentication token |

### Storage

Authentication data is stored in `localStorage`:

- **`mykobo_auth_token`**: JWT token
- **`mykobo_wallet_address`**: Authenticated wallet address

## Security Features

1. **Challenge-Response**: Each authentication uses a unique nonce
2. **Signature Verification**: Backend verifies wallet ownership through signatures
3. **JWT Tokens**: Secure session management with expiration
4. **Rate Limiting**: Backend enforces rate limits on auth endpoints
5. **Token Expiration**: Tokens expire after 24 hours
6. **Automatic Cleanup**: Expired tokens are automatically removed

## Error Handling

All auth functions throw `AuthError` with specific error codes:

```typescript
try {
  await authenticateWallet(walletAddress)
} catch (error) {
  if (error instanceof AuthError) {
    switch (error.code) {
      case 'NETWORK_ERROR':
        console.error('Network connection failed')
        break
      case 'SIGNING_FAILED':
        console.error('User rejected signature')
        break
      case 'VERIFICATION_FAILED':
        console.error('Signature verification failed')
        break
      case 'TOKEN_EXPIRED':
        console.error('Authentication token expired')
        break
    }
  }
}
```

## Development

### Build for Production
```bash
npm run build
```

### Preview Production Build
```bash
npm run preview
```

## Backend Requirements

The backend must provide these endpoints:

- `POST /auth/auth/challenge` - Request authentication challenge
- `POST /auth/auth/verify` - Verify signature and issue JWT

See backend documentation at `/tests/README.md` for implementation details.

## Notes

- Ethereum addresses are used (0x...)
- Signatures are converted to base64 for backend compatibility
- The frontend automatically handles token storage and renewal
- Rate limiting prevents abuse (5 challenges per minute)
