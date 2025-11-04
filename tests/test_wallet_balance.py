"""
Tests for wallet balance endpoint
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from flask import Flask


class TestWalletBalanceEndpoint:
    """Tests for the wallet balance endpoint"""

    @pytest.fixture
    def auth_headers(self, app):
        """Create authentication headers with a test token"""
        with app.app_context():
            import jwt
            from datetime import datetime, timedelta, UTC

            # Create a test token with valid-looking Solana address
            # This is a dummy but correctly formatted address
            payload = {
                'wallet_address': '11111111111111111111111111111111',
                'exp': datetime.now(UTC) + timedelta(hours=1)
            }
            token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

            return {'Authorization': f'Bearer {token}'}

    def test_get_wallet_balance_success(self, client, app, auth_headers):
        """Test successful wallet balance retrieval"""
        with app.app_context():
            # Mock Solana RPC responses
            mock_client = Mock()

            # Mock SOL balance response
            mock_sol_response = Mock()
            mock_sol_response.value = 1500000000  # 1.5 SOL in lamports
            mock_client.get_balance.return_value = mock_sol_response

            # Mock USDC balance response
            mock_usdc_response = Mock()
            mock_usdc_value = Mock()
            mock_usdc_value.amount = "100000000"  # 100 USDC with 6 decimals
            mock_usdc_value.decimals = 6
            mock_usdc_response.value = mock_usdc_value

            # Mock EURC balance response
            mock_eurc_response = Mock()
            mock_eurc_value = Mock()
            mock_eurc_value.amount = "50000000"  # 50 EURC with 6 decimals
            mock_eurc_value.decimals = 6
            mock_eurc_response.value = mock_eurc_value

            # Configure mock to return different responses for different calls
            mock_client.get_token_account_balance.side_effect = [mock_usdc_response, mock_eurc_response]

            # Patch the Solana Client
            with patch('solana.rpc.api.Client', return_value=mock_client):
                response = client.get('/solana/balance', headers=auth_headers)

                assert response.status_code == 200
                data = response.get_json()

                assert 'wallet_address' in data
                assert data['wallet_address'] == '11111111111111111111111111111111'

                assert 'balances' in data
                balances = data['balances']

                # Check SOL balance
                assert 'sol' in balances
                assert balances['sol']['amount'] == 1.5
                assert balances['sol']['decimals'] == 9
                assert '1.5' in balances['sol']['formatted']

                # Check USDC balance
                assert 'usdc' in balances
                assert balances['usdc']['amount'] == 100.0
                assert balances['usdc']['decimals'] == 6

                # Check EURC balance
                assert 'eurc' in balances
                assert balances['eurc']['amount'] == 50.0
                assert balances['eurc']['decimals'] == 6

    def test_get_wallet_balance_without_auth(self, client, app):
        """Test that balance endpoint requires authentication"""
        with app.app_context():
            response = client.get('/solana/balance')

            # Should redirect to home when no auth token
            assert response.status_code == 302
            assert response.location.endswith('/')

    def test_get_wallet_balance_with_no_token_accounts(self, client, app, auth_headers):
        """Test wallet balance when user has no token accounts"""
        with app.app_context():
            mock_client = Mock()

            # Mock SOL balance
            mock_sol_response = Mock()
            mock_sol_response.value = 500000000  # 0.5 SOL
            mock_client.get_balance.return_value = mock_sol_response

            # Mock token accounts not found (raise exception)
            mock_client.get_token_account_balance.side_effect = Exception("Account not found")

            with patch('solana.rpc.api.Client', return_value=mock_client):
                response = client.get('/solana/balance', headers=auth_headers)

                assert response.status_code == 200
                data = response.get_json()

                # Should return 0 for token balances
                assert data['balances']['sol']['amount'] == 0.5
                assert data['balances']['usdc']['amount'] == 0.0
                assert data['balances']['eurc']['amount'] == 0.0

    def test_get_wallet_balance_with_zero_balances(self, client, app, auth_headers):
        """Test wallet balance when all balances are zero"""
        with app.app_context():
            mock_client = Mock()

            # Mock zero SOL balance
            mock_sol_response = Mock()
            mock_sol_response.value = 0
            mock_client.get_balance.return_value = mock_sol_response

            # Mock zero token balances
            mock_token_response = Mock()
            mock_token_value = Mock()
            mock_token_value.amount = "0"
            mock_token_value.decimals = 6
            mock_token_response.value = mock_token_value

            mock_client.get_token_account_balance.side_effect = [mock_token_response, mock_token_response]

            with patch('solana.rpc.api.Client', return_value=mock_client):
                response = client.get('/solana/balance', headers=auth_headers)

                assert response.status_code == 200
                data = response.get_json()

                assert data['balances']['sol']['amount'] == 0.0
                assert data['balances']['usdc']['amount'] == 0.0
                assert data['balances']['eurc']['amount'] == 0.0

    def test_get_wallet_balance_rpc_error(self, client, app, auth_headers):
        """Test wallet balance when RPC returns an error"""
        with app.app_context():
            # Mock Client to raise an exception
            with patch('solana.rpc.api.Client', side_effect=Exception("RPC connection failed")):
                response = client.get('/solana/balance', headers=auth_headers)

                assert response.status_code == 500
                data = response.get_json()

                assert 'error' in data
                assert 'Failed to fetch wallet balance' in data['error']

    def test_get_wallet_balance_invalid_wallet_address(self, client, app):
        """Test wallet balance with invalid wallet address in token"""
        with app.app_context():
            import jwt
            from datetime import datetime, timedelta, UTC

            # Create token with invalid wallet address
            payload = {
                'wallet_address': 'invalid-address',
                'exp': datetime.now(UTC) + timedelta(hours=1)
            }
            token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
            headers = {'Authorization': f'Bearer {token}'}

            # Mock Client but Pubkey.from_string will fail
            with patch('solana.rpc.api.Client'):
                response = client.get('/solana/balance', headers=headers)

                # Should return 500 due to invalid address
                assert response.status_code == 500
                data = response.get_json()
                assert 'error' in data

    def test_get_wallet_balance_uses_config_values(self, client, app, auth_headers):
        """Test that balance endpoint uses configuration values correctly"""
        with app.app_context():
            # Set custom config values (use valid-format addresses)
            app.config["SOLANA_RPC_URL"] = "https://api.testnet.solana.com"
            app.config["USDC_TOKEN_MINT"] = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # Valid format
            app.config["EURC_TOKEN_MINT"] = "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr"  # Valid format

            mock_client = Mock()
            mock_sol_response = Mock()
            mock_sol_response.value = 1000000000
            mock_client.get_balance.return_value = mock_sol_response
            mock_client.get_token_account_balance.side_effect = Exception("Not found")

            with patch('solana.rpc.api.Client', return_value=mock_client) as mock_client_class:
                response = client.get('/solana/balance', headers=auth_headers)

                # Verify Client was initialized with correct RPC URL
                mock_client_class.assert_called_once_with("https://api.testnet.solana.com")

                assert response.status_code == 200

    def test_get_wallet_balance_large_amounts(self, client, app, auth_headers):
        """Test wallet balance with large token amounts"""
        with app.app_context():
            mock_client = Mock()

            # Mock large SOL balance
            mock_sol_response = Mock()
            mock_sol_response.value = 1000000000000000  # 1 million SOL
            mock_client.get_balance.return_value = mock_sol_response

            # Mock large USDC balance
            mock_usdc_response = Mock()
            mock_usdc_value = Mock()
            mock_usdc_value.amount = "999999999999"  # ~1 million USDC
            mock_usdc_value.decimals = 6
            mock_usdc_response.value = mock_usdc_value

            # Mock large EURC balance
            mock_eurc_response = Mock()
            mock_eurc_value = Mock()
            mock_eurc_value.amount = "888888888888"  # ~888k EURC
            mock_eurc_value.decimals = 6
            mock_eurc_response.value = mock_eurc_value

            mock_client.get_token_account_balance.side_effect = [mock_usdc_response, mock_eurc_response]

            with patch('solana.rpc.api.Client', return_value=mock_client):
                response = client.get('/solana/balance', headers=auth_headers)

                assert response.status_code == 200
                data = response.get_json()

                assert data['balances']['sol']['amount'] == 1000000.0
                assert data['balances']['usdc']['amount'] == 999999.999999
                assert data['balances']['eurc']['amount'] == 888888.888888
