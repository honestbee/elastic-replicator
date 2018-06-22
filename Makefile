# fixme - from repo url
# REPO ?= honestbee/search
REPO = $(shell git config --get remote.origin.url | awk -F":" '{print $$2}' | cut -d"." -f1)
IMAGE ?= $(REPO)
VERSION ?= latest
REGION ?= ap-southeast-1

build:
	docker build -t $(IMAGE):$(VERSION) .

validate:
	@test -n "$(ES_URL)" || (echo "ES_URL must be set"; exit 1)
	@test -n "$(SNAPSHOT_BUCKET)" || (echo "SNAPSHOT_BUCKET must be set"; exit 1)

snapshot: build validate
	docker run --rm $(IMAGE):$(VERSION) snapshot \
		--url $(ES_URL) \
		--bucket-name $(SNAPSHOT_BUCKET) \
		--region $(REGION) \
		--wait-for-cluster \
		--cleanup

restore: build validate
	docker run --rm $(IMAGE):$(VERSION) restore \
		--url $(ES_URL) \
		--bucket-name $(SNAPSHOT_BUCKET) \
		--region $(REGION) \
		--ignore-missing \
		--wait-for-cluster

list: build validate 
	docker run \
		--rm $(IMAGE):$(VERSION) ls \
		--url $(ES_URL) \
		--bucket-name $(SNAPSHOT_BUCKET) \
		--region $(REGION) \
		# --http-user $(HTTP_USER) \
		# --http-password $(HTTP_PASSWD)

cleanup: build validate 
	docker run --rm $(IMAGE):$(VERSION) cleanup \
		--url $(ES_URL) \
		--bucket-name $(SNAPSHOT_BUCKET) \
		--region $(REGION) \
		--keep=3
