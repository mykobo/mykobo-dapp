let timeout = null;
document.getElementById('amountInput').addEventListener('input', function (event) {
    clearTimeout(timeout);
    const amount = parseFloat(event.target.value);

    if (event.target.value === '') {
        document.getElementById('fee').innerText = '0.00';
        document.getElementById('total').innerText = '0.00';
        document.getElementById('error').innerText = '';
        return;
    }

    document.getElementById('fee').innerText = 'Calculating...';
    document.getElementById('total').innerText = 'Calculating...';
    document.getElementById('error').innerText = '';

    timeout = setTimeout(() => {
        if (isNaN(amount) || amount <= 0 || amount < minAmount || amount > maxAmount) {
            document.getElementById('fee').innerText = '0.00';
            document.getElementById('total').innerText = '0.00';
            document.getElementById('error').innerText = 'Invalid input. Please enter a positive number within the allowed range.';
            return;
        }

        const url = new URL(feeEndPoint, window.location.origin);
        url.searchParams.append('value', amount.toString());
        url.searchParams.append('kind', transactionKind);
        if (clientDomain) {
            url.searchParams.append('client_domain', clientDomain);
        }


        fetch(url.toString(), {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        })
            .then(response => response.json())
            .then(data => {
                console.log('Success:', data);
                document.getElementById('fee').innerText = data.total;
                document.getElementById('total').innerText = (amount - data.total).toFixed(2);
            })
            .catch((error) => {
                console.error('Error:', error);
                document.getElementById('fee').innerText = 'Error calculating fee';
            });
    }, 500);
});

document.querySelector('form').addEventListener('submit', function (event) {
    const submitButton = event.target.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    submitButton.innerText = 'Processing...';
});
