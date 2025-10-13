/**
 * Solana wallet configuration and utilities
 */

import {
  SolflareWalletAdapter
} from '@solana/wallet-adapter-wallets'
import { BaseMessageSignerWalletAdapter } from '@solana/wallet-adapter-base'
import { Connection, clusterApiUrl, PublicKey } from '@solana/web3.js'
import bs58 from 'bs58'

// Solana network configuration
export const SOLANA_NETWORK = import.meta.env.VITE_SOLANA_NETWORK || 'devnet'
export const SOLANA_RPC_URL =
  import.meta.env.VITE_SOLANA_RPC_URL ||
  clusterApiUrl(SOLANA_NETWORK as 'mainnet-beta' | 'devnet' | 'testnet')

// Solana connection
export const solanaConnection = new Connection(SOLANA_RPC_URL, 'confirmed')

// Available Solana wallet adapters
export const solanaWallets: BaseMessageSignerWalletAdapter[] = [
  new SolflareWalletAdapter()
]

// Current connected wallet
let currentWallet: BaseMessageSignerWalletAdapter | null = null

/**
 * Connect to a Solana wallet
 */
export async function connectSolanaWallet(
  adapter: BaseMessageSignerWalletAdapter
): Promise<string> {
  try {
    if (!adapter.connected) {
      await adapter.connect()
    }

    if (!adapter.publicKey) {
      throw new Error('Wallet public key not found')
    }

    currentWallet = adapter
    return adapter.publicKey.toBase58()
  } catch (error) {
    console.error('Failed to connect Solana wallet:', error)
    throw error
  }
}

/**
 * Disconnect from Solana wallet
 */
export async function disconnectSolanaWallet(): Promise<void> {
  if (currentWallet && currentWallet.connected) {
    await currentWallet.disconnect()
    currentWallet = null
  }
}

/**
 * Sign a message with Solana wallet
 */
export async function signSolanaMessage(message: string): Promise<string> {
  if (!currentWallet || !currentWallet.connected) {
    throw new Error('Wallet not connected')
  }

  if (!currentWallet.signMessage) {
    throw new Error('Wallet does not support message signing')
  }

  try {
    const encodedMessage = new TextEncoder().encode(message)
    const signature = await currentWallet.signMessage(encodedMessage)

    // Return signature as base64
    return Buffer.from(signature).toString('base64')
  } catch (error) {
    console.error('Failed to sign message:', error)
    throw error
  }
}

/**
 * Get current connected wallet
 */
export function getCurrentSolanaWallet(): BaseMessageSignerWalletAdapter | null {
  return currentWallet
}

/**
 * Get current wallet address
 */
export function getCurrentSolanaAddress(): string | null {
  if (!currentWallet || !currentWallet.publicKey) {
    return null
  }
  return currentWallet.publicKey.toBase58()
}

/**
 * Check if wallet is connected
 */
export function isSolanaWalletConnected(): boolean {
  return currentWallet !== null && currentWallet.connected
}

/**
 * Listen for wallet events
 */
export function setupSolanaWalletListeners(
  adapter: BaseMessageSignerWalletAdapter,
  callbacks: {
    onConnect?: (publicKey: PublicKey) => void
    onDisconnect?: () => void
    onError?: (error: Error) => void
  }
): void {
  adapter.on('connect', () => {
    if (adapter.publicKey && callbacks.onConnect) {
      callbacks.onConnect(adapter.publicKey)
    }
  })

  adapter.on('disconnect', () => {
    currentWallet = null
    if (callbacks.onDisconnect) {
      callbacks.onDisconnect()
    }
  })

  adapter.on('error', (error) => {
    if (callbacks.onError) {
      callbacks.onError(error)
    }
  })
}

/**
 * Verify a Solana signature (client-side verification)
 */
export function verifySolanaSignature(
  message: string,
  signature: string,
  publicKey: string
): boolean {
  try {
    const nacl = require('tweetnacl')
    const messageBytes = new TextEncoder().encode(message)
    const signatureBytes = bs58.decode(signature)
    const publicKeyBytes = new PublicKey(publicKey).toBytes()

    return nacl.sign.detached.verify(messageBytes, signatureBytes, publicKeyBytes)
  } catch (error) {
    console.error('Signature verification failed:', error)
    return false
  }
}
