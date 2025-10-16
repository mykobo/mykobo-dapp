build:
	cd wallet-connect && npm run build && cd ..
	cp ./app/templates/layouts/base.html ./app/templates/layouts/base.html.bak
	./extract-wagmi-script.sh ./wallet-connect/static/index.html ./app/templates/layouts/base.html
	cp -r ./wallet-connect/static/js ./app/static
	cp -r ./wallet-connect/static/css ./app/static

run:
	source .venv/bin/activate && HOSTNAME="127.0.0.1" ENV=development SERVICE_PORT=5001 ./boot.sh

release:
	semantic-release version --changelog