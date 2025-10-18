#!/bin/bash

if [ "${CIRCLE_BRANCH}" != "main" ]
then
    echo "VITE_API_BASE_URL=https://dev.mykobo.app" > ./wallet-connect/.env.production
    echo "VITE_SOLANA_NETWORK=devnet" >> ./wallet-connect/.env.production
    echo "VITE_SOLANA_RPC_URL=https://api.devnet.solana.com" >> ./wallet-connect/.env.production
    echo "VITE_ENABLE_ETHEREUM=false" >> ./wallet-connect/.env.production
    echo "VITE_ENABLE_SOLANA=true" >> ./wallet-connect/.env.production
    echo "VITE_WC_PROJECT_ID=${VITE_WC_PROJECT_ID}" >> ./wallet-connect/.env.production

else
    echo "VITE_API_BASE_URL=https://dapp-alb-dev-903454883.eu-west-1.elb.amazonaws.com" > ./wallet-connect/.env.production
    echo "VITE_SOLANA_NETWORK=mainnet" >> ./wallet-connect/.env.production
    echo "VITE_SOLANA_RPC_URL=https://api.mainnet-beta.solana.com" >> ./wallet-connect/.env.production
    echo "VITE_ENABLE_ETHEREUM=false" >> ./wallet-connect/.env.production
    echo "VITE_ENABLE_SOLANA=true" >> ./wallet-connect/.env.production
    echo "VITE_WC_PROJECT_ID=${VITE_WC_PROJECT_ID}" >> ./wallet-connect/.env.production
fi
ls -al ./wallet-connect
cat ./wallet-connect/.env.production