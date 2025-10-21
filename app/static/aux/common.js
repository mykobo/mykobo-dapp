function clearAuthToken(logoutUrl) {
    localStorage.removeItem('mykobo_auth_token');
    localStorage.removeItem('mykobo_wallet_address');
    window.location.href = logoutUrl;
}