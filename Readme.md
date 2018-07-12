**This repository is deprecated, please use https://github.com/honestbee/esctl instead**

# Elasticsearch Replicator

## Preconditions

- The replication job does not need AWS creds itself
- However, the ES clusters doing the snapshotting/restoration do
- S3 bucket must exist and the ES cluster must have AWS credentials allowing r/w access to it

## Usage

- Build:

    ```sh
    make build
    ```

- Take snapshot:

    ```sh
    ES_URL=<my-api-url> SNAPSHOT_BUCKET=<my-bucket-name> REGION=<my-region> make snapshot
    ```

- Restore from latest snapshot:

    ```sh
    ES_URL=<my-api-url> SNAPSHOT_BUCKET=<my-bucket-name> REGION=<my-region> make restore
    ```

## Kubernetes

- Make sure `kubectl config current-context` matches expectations
- Set up your environment:

    ```sh
    export ES_URL=http://es.example.com
    export IMAGE_NAME=http://registry.example.com/es-snapper
    export SNAPSHOT_BUCKET=my-es-replication-bucket
    ```

- List snapshots:

    ```sh
    kubectl run es-restore --image quay.io/honestbee/elasticsearch-snapper:v1.6.3 \
        -i --tty --rm --restart=Never -- \
        list \
        --bucket-name=$SNAPSHOT_BUCKET \
        --region=$REGION \
        --url=$ES_URL
    ```
