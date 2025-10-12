import { connect, disconnect, reconnect, watchAccount } from '@wagmi/core'
import { Buffer } from 'buffer'

import './style.css'
import { config } from './wagmi'
import {
  authenticateWallet,
  authenticateWalletUniversal,
  isAuthenticated,
  logout,
  clearAuthToken,
  AuthError,
  redirectToLobby,
  getAuthToken,
} from './auth'
import {
  solanaWallets,
  connectSolanaWallet,
  disconnectSolanaWallet,
  setupSolanaWalletListeners,
} from './solana'

// @ts-ignore
globalThis.Buffer = Buffer

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <div>
    <div id="account">
      <h2>Account</h2>

      <div>
        status:
        <br />
        addresses:
        <br />
        chainId:
      </div>
    </div>

    <div id="auth">
      <h2>Authentication</h2>
      <div id="auth-status">Not authenticated</div>
      <div id="auth-error" style="color: red;"></div>
    </div>

    <div id="connect">
      <h2>Connect Ethereum Wallet</h2>
      ${config.connectors
        .map(
          (connector) =>
            `<button class="connect" id="${connector.uid}" type="button">${connector.name}</button>`,
        )
        .join('')}
    </div>

    <div id="solana-connect" style="margin-top: 20px;">
      <h2>Connect Solana Wallet</h2>
      ${solanaWallets
        .map(
          (wallet) =>
            `<button class="solana-connect" id="${wallet.name}" type="button">${wallet.name}</button>`,
        )
        .join('')}
    </div>
  </div>
`

setupApp(document.querySelector<HTMLDivElement>('#app')!)

function setupApp(element: HTMLDivElement) {
  // Ethereum wallet connection
  const connectElement = element.querySelector<HTMLDivElement>('#connect')
  const buttons = element.querySelectorAll<HTMLButtonElement>('.connect')
  for (const button of buttons) {
    const connector = config.connectors.find(
      (connector) => connector.uid === button.id,
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

  // Solana wallet connection
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

        // Setup listeners
        setupSolanaWalletListeners(walletAdapter, {
          onConnect: (publicKey) => {
            const walletAddress = publicKey.toBase58()
            updateSolanaAccount(element, walletAddress)
            handleAuthenticationSolana(element, walletAddress)
          },
          onDisconnect: () => {
            updateSolanaAccount(element, null)
            logout()
            updateAuthStatus(element, false)
          },
          onError: (error) => {
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

  watchAccount(config, {
    onChange(account) {
      const accountElement = element.querySelector<HTMLDivElement>('#account')!
      accountElement.innerHTML = `
        <h2>Account</h2>
        <div>
          status: ${account.status}
          <br />
          addresses: ${
            account.addresses ? JSON.stringify(account.addresses) : ''
          }
          <br />
          chainId: ${account.chainId ?? ''}
        </div>
        ${
          account.status === 'connected'
            ? `<button id="disconnect" type="button">Disconnect</button>`
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

  reconnect(config)
    .then(() => {})
    .catch(() => {})
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

    // Check if already authenticated
    if (isAuthenticated()) {
      const token = getAuthToken()
      if (token) {
        authStatusElement.innerText = 'Redirecting to lobby...'
        await redirectToLobby(token)
      }
      return
    }

    // Show authenticating status
    authStatusElement.innerText = 'Authenticating...'

    // Perform authentication
    const token = await authenticateWallet(walletAddress)

    // Show success message briefly
    authStatusElement.innerText = '✓ Authentication successful! Redirecting...'

    // Wait 1 second to show success message, then redirect
    await new Promise(resolve => setTimeout(resolve, 1000))

    // Redirect to lobby with token
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

    // Check if already authenticated
    if (isAuthenticated()) {
      const token = getAuthToken()
      if (token) {
        authStatusElement.innerText = 'Redirecting to lobby...'
        await redirectToLobby(token)
      }
      return
    }

    authStatusElement.innerText = 'Authenticating Solana wallet...'

    // Perform Solana authentication
    const token = await authenticateWalletUniversal(walletAddress, 'solana')

    // Show success message briefly
    authStatusElement.innerText = '✓ Authentication successful! Redirecting...'

    // Wait 1 second to show success message, then redirect
    await new Promise(resolve => setTimeout(resolve, 1000))

    // Redirect to lobby with token
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
      <h2>Solana Account</h2>
      <div>
        status: connected
        <br />
        address: ${walletAddress}
        <br />
        <button id="disconnect-solana" type="button">Disconnect</button>
      </div>
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
      <h2>Account</h2>
      <div>
        status: disconnected
      </div>
    `
  }
}
