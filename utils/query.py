import requests

def query(
    url,
    method="GET"
):
    try:
        data = requests.request(method, url)
        if data.status_code == 200:
            return data.json()
        else:
            raise Exception(f"Error fetching data from {url}: {data.status_code}")
    except Exception as e:
        raise e
