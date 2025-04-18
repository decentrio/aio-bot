import requests
import logging

def query(
    baseurls: list,
    path="",
    method="GET",
    header=None,
    body=None
):
    for url in baseurls:
        try:
            # logging.info(f"Fetching data from {url + path}")
            data = requests.request(method, url + path, headers=header, json=body)
            if data.status_code == 200:
                return data.json()
            else:
                logging.error(f"Received non-200 data from {url + path}: {data.json()}")
                continue
        except Exception as e:
            logging.error(f"Error fetching data from {url + path}: {e}")
            continue
    raise Exception(f"Error fetching data from all URLs")
