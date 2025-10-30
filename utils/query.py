import logging
import requests
from requests.exceptions import RequestException

def query(
    baseurls: list,
    path="",
    method="GET",
    header=None,
    body=None
):
    should_reorder = isinstance(baseurls, list)
    urls = (
        [baseurls]
        if isinstance(baseurls, str)
        else baseurls
        if should_reorder
        else list(baseurls)
    )

    for idx, url in enumerate(urls):
        try:
            # logging.info(f"Fetching data from {url + path}")
            data = requests.request(method, url + path, headers=header, json=body, timeout=10)
            if data.status_code == 200:
                if should_reorder and idx != 0:
                    urls.insert(0, urls.pop(idx))
                return data.json()
            logging.error(f"Received non-200 data from {url + path}: {data.json()}")
        except RequestException as e:
            logging.warning(f"Error fetching data from {url + path}: {e}")
        except Exception as e:
            logging.warning(f"Unexpected error fetching data from {url + path}: {e}")
    raise Exception("Error fetching data from all URLs")
