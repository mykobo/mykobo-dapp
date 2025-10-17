import { baseAccount, walletConnect } from '@wagmi/connectors'
import { createConfig, http } from '@wagmi/core'
import { mainnet, sepolia } from '@wagmi/core/chains'

// Only create config if Ethereum is enabled
const ENABLE_ETHEREUM = import.meta.env.VITE_ENABLE_ETHEREUM === 'true'

export const config = ENABLE_ETHEREUM ? createConfig({
  chains: [mainnet, sepolia],
  connectors: [
    baseAccount(),
    walletConnect({ projectId: import.meta.env.VITE_WC_PROJECT_ID }),
  ],
  transports: {
    [mainnet.id]: http(),
    [sepolia.id]: http(),
  },
}) : null as any // Fallback to avoid import errors when Ethereum is disabled
