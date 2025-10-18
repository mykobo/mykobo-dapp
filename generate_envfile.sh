#!/bin/bash

if [ "${CIRCLE_BRANCH}" != "main" ]
then
    echo "VITE_API_BASE_URL=https://dev.mykobo.app" > ./wallet-connetct/.env.production
    echo "VITE_SOLANA_NETWORK=devnet" >> ./wallet-connetct/.env.production
    echo "VITE_SOLANA_RPC_URL=https://api.devnet.solana.com" >> ./wallet-connetct/.env.production
    echo "VITE_ENABLE_ETHEREUM=false" >> ./wallet-connetct/.env.production
    echo "VITE_ENABLE_SOLANA=true" >> ./wallet-connetct/.env.production
    echo "VITE_WC_PROJECT_ID=${VITE_WC_PROJECT_ID}" >> ./wallet-connetct/.env.production

else
    echo "VITE_API_BASE_URL=https://mykobo.app" > ./wallet-connetct/.env.production
    echo "VITE_SOLANA_NETWORK=mainnet" >> ./wallet-connetct/.env.production
    echo "VITE_SOLANA_RPC_URL=https://api.mainnet-beta.solana.com" >> ./wallet-connetct/.env.production
    echo "VITE_ENABLE_ETHEREUM=false" >> ./wallet-connetct/.env.production
    echo "VITE_ENABLE_SOLANA=true" >> ./wallet-connetct/.env.production
    echo "VITE_WC_PROJECT_ID=${VITE_WC_PROJECT_ID}" >> ./wallet-connetct/.env.production
fi
ls ./wallet-connect
cat ./wallet-connetct/.env.production