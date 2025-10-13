# Tests

Comprehensive test suite for MYKOBO DAPP authentication system.

## Running Tests

### Install test dependencies
```bash
uv sync --dev
```

### Run all tests
```bash
uv run pytest tests/
```

### Run specific test file
```bash
uv run pytest tests/test_auth.py
uv run pytest tests/test_decorators.py
```

### Run with verbose output
```bash
uv run pytest tests/ -v
```

### Run specific test class or function
```bash
uv run pytest tests/test_auth.py::TestGenerateAuthChallenge
uv run pytest tests/test_auth.py::TestGenerateAuthChallenge::test_generates_unique_nonces
```

### Run with coverage (optional)
```bash
uv run pytest tests/ --cov=app --cov-report=html
```

## Test Structure

### test_auth.py
Tests for `app/mod_common/auth.py` authentication functions and endpoints:

- **TestGenerateAuthChallenge**: Tests for challenge generation
- **TestVerifyWalletSignature**: Tests for signature verification
- **TestCleanupExpiredNonces**: Tests for nonce cleanup
- **TestAuthEndpoints**: Tests for `/auth/challenge` and `/auth/verify` endpoints
- **TestAuthIntegration**: Full authentication flow tests

### test_decorators.py
Tests for `app/decorators.py` authentication decorator:

- **TestRequireWalletAuthDecorator**: Tests for `@require_wallet_auth` decorator
- **TestDecoratorIntegration**: Integration tests with protected routes

## Test Coverage

Current test coverage: **39 tests**

- Challenge generation and validation
- Signature verification (success and failure cases)
- Nonce expiration and replay attack prevention
- JWT token creation and validation
- Rate limiting on auth endpoints
- Decorator authorization checks
- Full authentication flow integration
- Edge cases and error handling

## Fixtures

Key fixtures defined in `conftest.py`:

- `app`: Flask app instance for testing
- `client`: Test client for making HTTP requests
- `auth_headers`: Valid JWT authorization headers
- `expired_auth_headers`: Expired JWT headers for testing expiration

## Notes

- Tests use in-memory nonce store (cleared between tests)
- Rate limiting warnings are expected (in-memory storage)
- For production, configure Redis backend for rate limiting and nonce storage
