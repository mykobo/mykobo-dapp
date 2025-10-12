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

// API configuration
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

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
 * Sign a message using the connected wallet
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
 * Verify the signed message with the backend and receive JWT token
 *
 * @param walletAddress - The wallet address
 * @param signature - The signature hex string
 * @param nonce - The nonce from the challenge
 * @returns Verification response with JWT token
 * @throws AuthError if verification fails
 */
export async function verifySignature(
  walletAddress: string,
  signature: string,
  nonce: string
): Promise<VerificationResponse> {
  try {
    // Convert signature to base64 for backend
    const signatureBytes = signature.startsWith('0x')
      ? signature.slice(2)
      : signature
    const signatureBase64 = btoa(
      signatureBytes.match(/.{1,2}/g)!.map(byte =>
        String.fromCharCode(parseInt(byte, 16))
      ).join('')
    )

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
 * Complete authentication flow:
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
      challenge.nonce
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
