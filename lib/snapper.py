
import sys
import time
import json
from uuid import uuid4
import requests

def make_headers():
    """Generate the default headers for making requests to the ES API"""
    return {'Content-type': 'application/json'}


class Snapper:
    """Tool to manage snapshots on a ES cluster"""

    def __init__(self, options):
        self._cluster_url = options["url"]
        self._repo_name = options["repo_name"]
        self._bucket_name = options["bucket_name"]
        self._region = options["region"]

        if "wait_for_cluster" in options:
            self._wait_for_cluster = True


    def snapshot(self):
        """Do a snapshot"""

        # Wait for cluster to become available
        if self._wait_for_cluster:
            self._do_wait_for_cluster()

        name = str(uuid4())
        repo_url = self._repo_url()
        snapshot_url = repo_url+"/"+name

        self._ensure_repo()

        # PUT snapshot url creates the snapshot
        print("Snapshot url: "+snapshot_url)
        res = self._do_put(snapshot_url)

        # Poll snapshot state and wait until it changes to 'SUCCESS'
        print("Waiting for snapshot to complete ...")
        while True:
            res = self._do_get(snapshot_url)
            data = res.json()
            state = data["snapshots"][0]["state"]

            if state == "SUCCESS":
                print("Snapshot complete: "+snapshot_url)
                break
            elif state == "IN_PROGRESS":
                time.sleep(2)
                continue
            else:
                raise Exception("Unexpected snapshot state: "+state)


    def restore(self, name="latest", ignore_missing=False, wait_for="green"):
        """Do a restore"""

        # An existing S3 bucket might already hold snapshots we can use to restore
        # Check if snapshot repo already exists, if not, create it
        repo_url = self._repo_url()
        self._ensure_repo()

        snapshot_info = None

        # Find requested version or use the latest one if version == 'latest'
        if name == 'latest':
            snapshot_info = self._find_latest_snapshot()
        else:
            snapshot_info = self._get_snapshot(repo_url, name)

        if not snapshot_info:
            if not ignore_missing:
                raise Exception("No snapshots found")
            else:
                print("No snapshot to restore, ignoring")
                return

        snapshot_name = snapshot_info["snapshot"]
        indices = snapshot_info["indices"]
        start_time = snapshot_info["start_time"]

        print("Restoring snapshot "+snapshot_name+" taken "+start_time)
        self._close_indices(indices)

        # restore snapshot
        restore_url = self._snapshot_url(snapshot_name)+"/_restore"
        self._do_post(restore_url)

        if wait_for == "red" or not wait_for:
            return # no need to wait

        print("Waiting for cluster to become "+wait_for)
        self._do_wait_for_status(wait_for)

        print("Done restoring from snapshot "+snapshot_name)


    def list_snapshots(self, sort_reverse=False):
        """List all snapshots"""
        repo_url = self._repo_url()
        self._ensure_repo()

        res = self._do_get(repo_url+"/_all")
        data = res.json()

        sorted_snaps = sorted(
            data["snapshots"],
            key=lambda s: s["start_time"],
            reverse=sort_reverse
        )

        return sorted_snaps


    def cleanup(self, keep=5):
        """Cleanup old snapshots"""
        snaps = self.list_snapshots(sort_reverse=True)
        delete = snaps[keep:]

        print("Cleaning up, will keep {} latest snapshot(s)".format(keep))
        for snap in delete:
            self._delete_snapshot(snap["snapshot"])
            print("Snapshot {} from {} deleted".format(snap["snapshot"], snap["start_time"]))


    def _do_get(self, url, expected=200):
        """Make a GET request"""
        headers = make_headers()
        res = requests.get(url, headers=headers)
        return self._check_status(res, expected)


    def _do_put(self, url, payload=None, expected=200):
        """Make a PUT request"""
        headers = make_headers()
        if payload:
            payload = json.dumps(payload)
        res = requests.put(url, data=payload, headers=headers)
        return self._check_status(res, expected)


    def _do_post(self, url, payload=None, expected=(200, 201)):
        """Make a POST request"""
        headers = make_headers()
        if payload:
            payload = json.dumps(payload)
        res = requests.post(url, data=payload, headers=headers)
        return self._check_status(res, expected)


    def _do_delete(self, url, expected=200):
        """Make a DELETE request"""
        headers = make_headers()
        res = requests.delete(url, headers=headers)
        return self._check_status(res, expected)


    def _check_status(self, res, expected=(200, 201), message="Unexpected response status"):
        """Check if response status code is within expected values, of not raises an Exception"""
        if expected is None:
            return res
        if isinstance(expected, int):
            expected = [expected]

        if res.status_code not in expected:
            print(res.text, file=sys.stderr)
            raise Exception(message)

        return res


    def _repo_url(self):
        """Generates the repo url for a snapshot repo based on the given options"""
        return self._cluster_url+"/_snapshot/"+self._repo_name


    def _index_url(self, index_name):
        """Generates the url to the given index using the url from options"""
        return self._cluster_url+"/"+index_name


    def _healthcheck_url(self):
        """Generates the health check endpoint url"""
        return self._cluster_url+"/_cat/health"


    def _snapshot_url(self, snapshot_name):
        """Generates the url for given snapshot"""
        repo_url = self._repo_url()
        return repo_url+"/"+snapshot_name


    def _ensure_repo(self):
        """Ensure the elasticsearch snapshot repo at the given url actually exists, if it doesn't,
        create it"""

        print("Ensure repo exists")
        repo_url = self._repo_url()
        res = self._do_get(repo_url, expected=(200, 404))

        if res.status_code == 404:
            print("Creating snapshot repository")
            settings = {
                "type": "s3",
                "settings": {
                    "bucket": self._bucket_name,
                    "region": self._region
                }
            }
            res = self._do_put(repo_url, payload=settings)
            print("Repo created")
        else:
            print("Repo already exists")


    def _find_latest_snapshot(self):
        """Find the latest snapshot in the repo at the given url. Returns None if there are no
        snapshots."""
        snapshots = self.list_snapshots(sort_reverse=True)
        if not snapshots:
            return None
        else:
            return snapshots[0]


    def _get_snapshot(self, repo_url, name):
        """Find the snapshot with the given name. Raises an error if the snapshot was not found"""

        url = repo_url+'/'+name
        res = self._do_get(url, expected=(200, 404))

        if res.status_code == 404:
            return None
        else:
            data = res.json()
            return data["snapshots"][0]


    def _do_wait_for_status(self, expected_state="green"):
        """Poll cluster health state and only terminate when given state is reached"""
        health_url = self._healthcheck_url()
        while True:
            res = self._do_get(health_url)
            data = res.json()
            if data[0]["status"] != expected_state:
                time.sleep(5)
            else:
                break


    def _do_wait_for_cluster(self):
        """Probe cluster health endpoint, return only when status is 200"""

        health_url = self._healthcheck_url()

        print("Waiting for cluster to become available")

        while True:
            res = self._do_get(health_url, expected=None)
            status_code = res.status_code
            if status_code != 200:
                print("Cluster response is "+str(status_code)+", waiting")
                time.sleep(5)
            else:
                print("Cluster available")
                break


    def _close_indices(self, indices):
        """Close list of indices on cluster at given url. If index does not exist it is ignored"""
        for index_name in indices:
            print("Closing index "+index_name)
            index_url = self._index_url(index_name)
            self._do_post(index_url+"/_close", expected=(200, 404))


    def _delete_snapshot(self, name):
        """Delete snapshot given by name"""
        url = self._snapshot_url(name)
        self._do_delete(url)