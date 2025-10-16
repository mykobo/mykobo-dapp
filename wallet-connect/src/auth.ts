/**
 * Authentication module for wallet-connected users
 *
 * This module handles the authentication flow with the Flask backend:
 * 1. Request a challenge from the backend
 * 2. Sign the challenge with the connected wallet
 * 3. Verify the signature and receive a JWT token
 */

import { signMessage } from '@wagmi/core'
import { config } from './wagmi'
import { signSolanaMessage } from './solana'

// API configuration
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Wallet types
export type WalletType = 'ethereum' | 'solana'

// Storage keys
const AUTH_TOKEN_KEY = 'mykobo_auth_token'
const WALLET_ADDRESS_KEY = 'mykobo_wallet_address'

/**
 * Challenge response from backend
 */
interface Challenge {
  nonce: string
  message: string
  timestamp: number
}

/**
 * Challenge API response
 */
interface ChallengeResponse {
  challenge: Challenge
  expires_in: number
}

/**
 * Verification API response
 */
interface VerificationResponse {
  token: string
  wallet_address: string
  expires_in: number
}

/**
 * Authentication error
 */
export class AuthError extends Error {
  constructor(message: string, public code?: string) {
    super(message)
    this.name = 'AuthError'
  }
}

/**
 * Request an authentication challenge from the backend
 *
 * @param walletAddress - The wallet address to authenticate
 * @returns Challenge data to be signed
 * @throws AuthError if request fails
 */
export async function requestChallenge(walletAddress: string): Promise<Challenge> {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/auth/challenge`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ wallet_address: walletAddress }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new AuthError(
        error.error || 'Failed to request challenge',
        response.status.toString()
      )
    }

    const data: ChallengeResponse = await response.json()
    return data.challenge
  } catch (error) {
    if (error instanceof AuthError) throw error
    throw new AuthError(
      `Network error: ${(error as Error).message}`,
      'NETWORK_ERROR'
    )
  }
}

/**
 * Sign a message using the connected Ethereum wallet
 *
 * @param message - The message to sign
 * @param address - The wallet address
 * @returns Signature as a hex string
 * @throws AuthError if signing fails
 */
export async function signAuthMessage(
  message: string,
  address: `0x${string}`
): Promise<string> {
  try {
    const signature = await signMessage(config, {
      message,
      account: address,
    })
    return signature
  } catch (error) {
    throw new AuthError(
      `Failed to sign message: ${(error as Error).message}`,
      'SIGNING_FAILED'
    )
  }
}

/**
 * Sign a message with the appropriate wallet type
 *
 * @param message - The message to sign
 * @param address - The wallet address
 * @param walletType - Type of wallet (ethereum or solana)
 * @returns Signature (base64 for Solana, hex for Ethereum)
 * @throws AuthError if signing fails
 */
export async function signMessageForWalletType(
  message: string,
  address: string,
  walletType: WalletType
): Promise<string> {
  try {
    if (walletType === 'solana') {
      // Solana returns base64 signature directly
      return await signSolanaMessage(message)
    } else {
      // Ethereum
      return await signAuthMessage(message, address as `0x${string}`)
    }
  } catch (error) {
    throw new AuthError(
      `Failed to sign message: ${(error as Error).message}`,
      'SIGNING_FAILED'
    )
  }
}

/**
 * Verify the signed message with the backend and receive JWT token
 *
 * @param walletAddress - The wallet address
 * @param signature - The signature (hex for Ethereum, base64 for Solana)
 * @param nonce - The nonce from the challenge
 * @param walletType - Type of wallet (ethereum or solana)
 * @returns Verification response with JWT token
 * @throws AuthError if verification fails
 */
export async function verifySignature(
  walletAddress: string,
  signature: string,
  nonce: string,
  walletType: WalletType = 'ethereum'
): Promise<VerificationResponse> {
  try {
    let signatureBase64: string

    if (walletType === 'solana') {
      // Solana signature is already in base64
      signatureBase64 = signature
    } else {
      // Convert Ethereum hex signature to base64
      const signatureBytes = signature.startsWith('0x')
        ? signature.slice(2)
        : signature
      signatureBase64 = btoa(
        signatureBytes.match(/.{1,2}/g)!.map(byte =>
          String.fromCharCode(parseInt(byte, 16))
        ).join('')
      )
    }

    const response = await fetch(`${API_BASE_URL}/auth/auth/verify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        wallet_address: walletAddress,
        signature: signatureBase64,
        nonce,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new AuthError(
        error.error || 'Failed to verify signature',
        response.status.toString()
      )
    }

    const data: VerificationResponse = await response.json()
    return data
  } catch (error) {
    if (error instanceof AuthError) throw error
    throw new AuthError(
      `Verification error: ${(error as Error).message}`,
      'VERIFICATION_FAILED'
    )
  }
}

/**
 * Complete authentication flow (Ethereum-only):
 * 1. Request challenge
 * 2. Sign challenge
 * 3. Verify signature
 * 4. Store JWT token
 *
 * @param walletAddress - The wallet address to authenticate
 * @returns JWT token
 * @throws AuthError if any step fails
 */
export async function authenticateWallet(
  walletAddress: `0x${string}`
): Promise<string> {
  try {
    console.log(`Starting authentication for wallet: ${walletAddress}`)

    // Step 1: Request challenge
    const challenge = await requestChallenge(walletAddress)
    console.log('Challenge received:', challenge.nonce)

    // Step 2: Sign the challenge message
    const signature = await signAuthMessage(challenge.message, walletAddress)
    console.log('Message signed')

    // Step 3: Verify signature and get JWT
    const verification = await verifySignature(
      walletAddress,
      signature,
      challenge.nonce,
      'ethereum'
    )
    console.log('Authentication successful')

    // Step 4: Store token and wallet address
    storeAuthToken(verification.token, walletAddress)

    return verification.token
  } catch (error) {
    console.error('Authentication failed:', error)
    throw error
  }
}

/**
 * Universal authentication flow supporting both Ethereum and Solana:
 * 1. Request challenge
 * 2. Sign challenge with appropriate wallet
 * 3. Verify signature
 * 4. Store JWT token
 *
 * @param walletAddress - The wallet address to authenticate
 * @param walletType - Type of wallet (ethereum or solana)
 * @returns JWT token
 * @throws AuthError if any step fails
 */
export async function authenticateWalletUniversal(
  walletAddress: string,
  walletType: WalletType
): Promise<string> {
  try {
    console.log(`Starting ${walletType} authentication for wallet: ${walletAddress}`)

    // Step 1: Request challenge
    const challenge = await requestChallenge(walletAddress)
    console.log('Challenge received:', challenge.nonce)

    // Step 2: Sign the challenge message with appropriate wallet
    const signature = await signMessageForWalletType(
      challenge.message,
      walletAddress,
      walletType
    )
    console.log('Message signed: ' + signature + ' wallet type: ', walletType)

    // Step 3: Verify signature and get JWT
    const verification = await verifySignature(
      walletAddress,
      signature,
      challenge.nonce,
      walletType
    )
    console.log('Authentication successful')

    // Step 4: Store token and wallet address
    storeAuthToken(verification.token, walletAddress)

    return verification.token
  } catch (error) {
    console.error('Authentication failed:', error)
    throw error
  }
}

/**
 * Store authentication token in localStorage
 *
 * @param token - JWT token
 * @param walletAddress - Wallet address
 */
export function storeAuthToken(token: string, walletAddress: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token)
  localStorage.setItem(WALLET_ADDRESS_KEY, walletAddress)
}

/**
 * Get stored authentication token
 *
 * @returns JWT token or null if not found
 */
export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY)
}

/**
 * Get stored wallet address
 *
 * @returns Wallet address or null if not found
 */
export function getStoredWalletAddress(): string | null {
  return localStorage.getItem(WALLET_ADDRESS_KEY)
}

/**
 * Clear authentication data from localStorage
 */
export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY)
  localStorage.removeItem(WALLET_ADDRESS_KEY)
}

/**
 * Check if user is authenticated
 *
 * @returns true if JWT token exists
 */
export function isAuthenticated(): boolean {
  return getAuthToken() !== null
}

/**
 * Make an authenticated API request
 *
 * @param endpoint - API endpoint (e.g., '/api/transaction')
 * @param options - Fetch options
 * @returns Response
 * @throws AuthError if not authenticated or request fails
 */
export async function authenticatedFetch(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = getAuthToken()

  if (!token) {
    throw new AuthError('Not authenticated', 'NOT_AUTHENTICATED')
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  })

  // If token expired, clear stored auth
  if (response.status === 401) {
    clearAuthToken()
    throw new AuthError('Authentication expired', 'TOKEN_EXPIRED')
  }

  return response
}

/**
 * Logout user by clearing auth token
 */
export function logout(): void {
  clearAuthToken()
  console.log('Logged out')
}

/**
 * Navigate to dashboard with auth token
 * Redirects to backend /user/dashboard route
 *
 * @param token - JWT token (stored in localStorage, sent via cookie)
 * @param _walletAddress - Optional wallet address (unused, kept for compatibility)
 */
export async function redirectToLobby(token: string, _walletAddress?: string): Promise<void> {
  try {
    console.log('Redirecting to /user/dashboard...')

    // Set token as a cookie for the backend to read
    // The token is also stored in localStorage for client-side API calls
    const isSecure = API_BASE_URL.startsWith('https')
    const secureFlag = isSecure ? '; secure' : ''
    document.cookie = `auth_token=${token}; path=/${secureFlag}; samesite=lax`

    // Redirect to Flask backend lobby route without token in URL
    window.location.href = `${API_BASE_URL}/user/dashboard`
  } catch (error) {
    console.error('Failed to redirect to dashboard:', error)
    throw error
  }
}

