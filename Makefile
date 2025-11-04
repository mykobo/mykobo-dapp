build:
	@cd wallet-connect && npm run build && cd ..
	@cp ./app/templates/layouts/base.html ./app/templates/layouts/base.html.bak && echo "Copied base template"
	@./extract-wagmi-script.sh ./wallet-connect/static/index.html ./app/templates/layouts/base.html
	@cp -r ./wallet-connect/static/js ./app/static && echo "Copied javascript files"
	@cp -r ./wallet-connect/static/css ./app/static && echo "Copied stylesheet"

run_dapp:
	@source .venv/bin/activate && HOSTNAME="127.0.0.1" ENV=local SERVICE_PORT=5001 ./boot.sh

run_transaction_processor:
	@source .venv/bin/activate && ./entrypoint.sh transaction-processor

run_consumer:
	@source .venv/bin/activate && ./entrypoint.sh inbox-consumer

release:
	@semantic-release version --changelog

test:
	@ENV=development poetry run pytest -v --tb=line
