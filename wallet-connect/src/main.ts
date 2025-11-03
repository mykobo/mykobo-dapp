import { connect, disconnect, reconnect, watchAccount } from '@wagmi/core'
import { Buffer } from 'buffer'

import './style.css'
import { config } from './wagmi'
import {
  authenticateWallet,
  authenticateWalletUniversal,
  logout,
  clearAuthToken,
  AuthError,
  redirectToLobby,
} from './auth'
import {
  solanaWallets,
  connectSolanaWallet,
  disconnectSolanaWallet,
  setupSolanaWalletListeners as setupWalletEventListeners,
} from './solana'

// @ts-ignore
globalThis.Buffer = Buffer

// Feature flags
const ENABLE_ETHEREUM = import.meta.env.VITE_ENABLE_ETHEREUM === 'true'
const ENABLE_SOLANA = import.meta.env.VITE_ENABLE_SOLANA === 'true'

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <div class="app-container">
    <div class="header">
      <img src="/static/images/mykobo_logo_white.svg" alt="MYKOBO" style="width: 150px; display: block; margin: 0 auto;" />
      <p class="subtitle">Stable coin infrastructure providers</p>
    </div>

    <div id="account" class="status-card">
      <h2>Account Status</h2>
      <div class="status-content">
        <span class="status-label">Status:</span> <span class="status-value">disconnected</span>
        <br />
        <span class="status-label">Address:</span> <span class="status-value">-</span>
        <br />
        <span class="status-label">Chain:</span> <span class="status-value">-</span>
      </div>
    </div>

    <div id="auth" class="status-card">
      <h2>Authentication</h2>
      <div id="auth-status" class="auth-status">Not authenticated</div>
      <div id="auth-error" class="auth-error"></div>
    </div>

    ${ENABLE_ETHEREUM ? `
    <div id="connect" class="wallet-section">
      <h2>Connect Ethereum Wallet</h2>
      <div class="wallet-buttons">
        ${config?.connectors
          .map(
            (connector: any) =>
              `<button class="wallet-button connect" id="${connector.uid}" type="button">
                <span class="wallet-name">${connector.name}</span>
              </button>`,
          )
          .join('') ?? ''}
      </div>
    </div>
    ` : ''}

    ${ENABLE_SOLANA ? `
    <div id="solana-connect" class="wallet-section">
      <h2>Connect Solana Wallet</h2>
      <div id="solana-wallet-buttons" class="wallet-buttons">
        <!-- Wallet buttons will be inserted here after detection -->
      </div>
    </div>
    ` : ''}
  </div>
`

setupApp(document.querySelector<HTMLDivElement>('#app')!)

function setupApp(element: HTMLDivElement) {
  // Setup Solana wallet buttons if enabled
  if (ENABLE_SOLANA) {
    // Wait for wallet extensions to load, then setup Solana wallet buttons
    setTimeout(() => {
      setupSolanaWalletButtons(element)
    }, 100)
  }

  // Setup Ethereum wallet connection if enabled
  if (ENABLE_ETHEREUM && config) {
    const connectElement = element.querySelector<HTMLDivElement>('#connect')
    const buttons = element.querySelectorAll<HTMLButtonElement>('.connect')
    for (const button of buttons) {
      const connector = config.connectors.find(
        (connector: any) => connector.uid === button.id,
      )!
      button.addEventListener('click', async () => {
        try {
          const errorElement = element.querySelector<HTMLDivElement>('#error')
          if (errorElement) errorElement.remove()
          await connect(config, { connector })
        } catch (error) {
          const errorElement = document.createElement('div')
          errorElement.id = 'error'
          errorElement.innerText = (error as Error).message
          connectElement?.appendChild(errorElement)
        }
      })
    }

    // Watch Ethereum account changes
    watchAccount(config, {
    onChange(account) {
      const accountElement = element.querySelector<HTMLDivElement>('#account')!
      accountElement.innerHTML = `
        <h2>Account Status</h2>
        <div class="status-content">
          <span class="status-label">Status:</span> <span class="status-value">${account.status}</span>
          <br />
          <span class="status-label">Address:</span> <span class="status-value">${
            account.addresses ? account.addresses[0] : '-'
          }</span>
          <br />
          <span class="status-label">Chain:</span> <span class="status-value">${account.chainId ?? '-'}</span>
        </div>
        ${
          account.status === 'connected'
            ? `<button id="disconnect" class="disconnect-button" type="button">Disconnect Wallet</button>`
            : ''
        }
      `

      const disconnectButton =
        element.querySelector<HTMLButtonElement>('#disconnect')
      if (disconnectButton) {
        disconnectButton.addEventListener('click', () => {
          disconnect(config)
          logout()
          updateAuthStatus(element, false)
        })
      }

      // Trigger authentication when wallet connects
      if (account.status === 'connected' && account.addresses?.[0]) {
        handleAuthentication(element, account.addresses[0])
      } else {
        // Clear auth when disconnected
        updateAuthStatus(element, false)
      }
    },
  })

    // Attempt to reconnect on page load
    reconnect(config)
      .then(() => {})
      .catch(() => {})
  }
}

/**
 * Setup Solana wallet buttons with proper detection
 */
function setupSolanaWalletButtons(element: HTMLDivElement): void {
  const buttonsContainer = element.querySelector<HTMLDivElement>('#solana-wallet-buttons')
  if (!buttonsContainer) return

  // Generate buttons with current readyState
  const buttonsHTML = solanaWallets
    .map((wallet) => {
      const isReady = wallet.readyState === 'Installed'
      const status = isReady ? '' : '<span class="wallet-status"> (Not Installed)</span>'
      console.log(`Solana wallet ${wallet.name}: readyState = ${wallet.readyState}`)
      return `<button class="wallet-button solana-connect" id="${wallet.name}" type="button" ${!isReady ? 'disabled' : ''}>
        <span class="wallet-name">${wallet.name}${status}</span>
      </button>`
    })
    .join('')

  buttonsContainer.innerHTML = buttonsHTML

  // Setup event listeners for Solana wallet connection
  setupSolanaWalletListeners(element)
}

/**
 * Setup event listeners for Solana wallet buttons
 */
function setupSolanaWalletListeners(element: HTMLDivElement): void {
  const solanaConnectElement = element.querySelector<HTMLDivElement>('#solana-connect')
  const solanaButtons = element.querySelectorAll<HTMLButtonElement>('.solana-connect')

  for (const button of solanaButtons) {
    button.addEventListener('click', async () => {
      try {
        const errorElement = element.querySelector<HTMLDivElement>('#solana-error')
        if (errorElement) errorElement.remove()

        const walletAdapter = solanaWallets.find((w) => w.name === button.id)
        if (!walletAdapter) {
          throw new Error('Wallet adapter not found')
        }

        // Setup event listeners for wallet connection/disconnection
        setupWalletEventListeners(walletAdapter, {
          onConnect: (publicKey: import('@solana/web3.js').PublicKey) => {
            const walletAddress = publicKey.toBase58()
            updateSolanaAccount(element, walletAddress)
            handleAuthenticationSolana(element, walletAddress)
          },
          onDisconnect: () => {
            updateSolanaAccount(element, null)
            logout()
            updateAuthStatus(element, false)
          },
          onError: (error: Error) => {
            console.error('Solana wallet error:', error)
          },
        })

        // Connect to wallet
        const walletAddress = await connectSolanaWallet(walletAdapter)
        updateSolanaAccount(element, walletAddress)
        await handleAuthenticationSolana(element, walletAddress)
      } catch (error) {
        const errorElement = document.createElement('div')
        errorElement.id = 'solana-error'
        errorElement.style.color = 'red'
        errorElement.innerText = `Solana error: ${(error as Error).message}`
        solanaConnectElement?.appendChild(errorElement)
      }
    })
  }
}

/**
 * Handle authentication after wallet connection
 */
async function handleAuthentication(
  element: HTMLDivElement,
  walletAddress: `0x${string}`
) {
  const authStatusElement = element.querySelector<HTMLDivElement>('#auth-status')!
  const authErrorElement = element.querySelector<HTMLDivElement>('#auth-error')!

  try {
    // Clear any previous errors
    authErrorElement.innerText = ''

    // Show authenticating status
    authStatusElement.innerText = 'Authenticating...'

    // Perform authentication
    const token = await authenticateWallet(walletAddress)

    // Show success message
    authStatusElement.innerText = '✓ Authentication successful! Redirecting to lobby...'

    // Wait 2 seconds before redirecting
    await new Promise(resolve => setTimeout(resolve, 2000))

    // Redirect to lobby
    await redirectToLobby(token)
  } catch (error) {
    console.error('Authentication error:', error)

    if (error instanceof AuthError) {
      authErrorElement.innerText = `Authentication failed: ${error.message}`
    } else {
      authErrorElement.innerText = `Authentication failed: ${(error as Error).message}`
    }

    updateAuthStatus(element, false, 'Failed')
  }
}

/**
 * Update authentication status in UI
 */
function updateAuthStatus(
  element: HTMLDivElement,
  authenticated: boolean,
  customStatus?: string
) {
  const authStatusElement = element.querySelector<HTMLDivElement>('#auth-status')!
  const authErrorElement = element.querySelector<HTMLDivElement>('#auth-error')!

  if (authenticated) {
    authStatusElement.innerHTML = `
      ✓ Authenticated
      <br />
      <button id="logout-btn" type="button" style="margin-top: 10px;">Logout</button>
    `
    authErrorElement.innerText = ''

    // Add logout handler
    const logoutBtn = element.querySelector<HTMLButtonElement>('#logout-btn')
    if (logoutBtn) {
      logoutBtn.addEventListener('click', () => {
        logout()
        clearAuthToken()
        updateAuthStatus(element, false)
      })
    }
  } else {
    authStatusElement.innerText = customStatus || 'Not authenticated'
  }
}

/**
 * Handle Solana wallet authentication
 */
async function handleAuthenticationSolana(
  element: HTMLDivElement,
  walletAddress: string
) {
  const authStatusElement = element.querySelector<HTMLDivElement>('#auth-status')!
  const authErrorElement = element.querySelector<HTMLDivElement>('#auth-error')!

  try {
    authErrorElement.innerText = ''

    authStatusElement.innerText = 'Authenticating Solana wallet...'

    // Perform Solana authentication
    const token = await authenticateWalletUniversal(walletAddress, 'solana')

    // Show success message
    authStatusElement.innerText = '✓ Authentication successful! Redirecting to lobby...'

    // Wait 2 seconds before redirecting
    await new Promise(resolve => setTimeout(resolve, 2000))

    // Redirect to lobby
    await redirectToLobby(token)
  } catch (error) {
    console.error('Solana authentication error:', error)

    if (error instanceof AuthError) {
      authErrorElement.innerText = `Authentication failed: ${error.message}`
    } else {
      authErrorElement.innerText = `Authentication failed: ${(error as Error).message}`
    }

    updateAuthStatus(element, false, 'Failed')
  }
}

/**
 * Update Solana account display
 */
function updateSolanaAccount(
  element: HTMLDivElement,
  walletAddress: string | null
) {
  const accountElement = element.querySelector<HTMLDivElement>('#account')!

  if (walletAddress) {
    accountElement.innerHTML = `
      <h2>Account Status</h2>
      <div class="status-content">
        <span class="status-label">Status:</span> <span class="status-value status-connected">connected</span>
        <br />
        <span class="status-label">Address:</span> <span class="status-value">${walletAddress}</span>
        <br />
        <span class="status-label">Chain:</span> <span class="status-value">Solana</span>
      </div>
      <button id="disconnect-solana" class="disconnect-button" type="button">Disconnect Wallet</button>
    `

    const disconnectButton = element.querySelector<HTMLButtonElement>('#disconnect-solana')
    if (disconnectButton) {
      disconnectButton.addEventListener('click', async () => {
        await disconnectSolanaWallet()
        updateSolanaAccount(element, null)
        logout()
        updateAuthStatus(element, false)
      })
    }
  } else {
    accountElement.innerHTML = `
      <h2>Account Status</h2>
      <div class="status-content">
        <span class="status-label">Status:</span> <span class="status-value">disconnected</span>
        <br />
        <span class="status-label">Address:</span> <span class="status-value">-</span>
        <br />
        <span class="status-label">Chain:</span> <span class="status-value">-</span>
      </div>
    `
  }
}
