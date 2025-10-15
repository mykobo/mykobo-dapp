#!/bin/bash

if [ "${CIRCLE_BRANCH}" != "main" ]
then
    echo "VITE_API_BASE_URL=https://dev.mykobo.app" > .env.production
    echo "VITE_SOLANA_NETWORK=devnet" >> .env.production
    echo "VITE_SOLANA_RPC_URL=https://api.devnet.solana.com" >> .env.production
    echo "VITE_ENABLE_ETHEREUM=false" >> .env.production
    echo "VITE_ENABLE_SOLANA=true" >> .env.production

else
    echo "VITE_API_BASE_URL=https://mykobo.app" > .env.production
    echo "VITE_SOLANA_NETWORK=mainnet" >> .env.production
    echo "VITE_SOLANA_RPC_URL=https://api.mainnet-beta.solana.com" >> .env.production
    echo "VITE_ENABLE_ETHEREUM=false" >> .env.production
    echo "VITE_ENABLE_SOLANA=true" >> .env.production
fi

cat .env.production