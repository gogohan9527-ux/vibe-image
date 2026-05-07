import json
from datetime import datetime
from pathlib import Path

import requests


API_KEY = "sk-ElshMFKYibCphqP6SXHDOsTkB5mLTJ50sNVfjqwYv88NULwR"
URL = "https://momoapi.top/v1/images/generations"
OUTPUT_DIR = Path(__file__).parent / "images"


payload = json.dumps(
    {
        "model": "t8-/gpt-image-2",
        "prompt": "A cute cat playing in a garden",
        "n": 1,
        "size": "1024x1024",
        "quality": "low",
        "format": "jpeg",
    }
)

headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def get_image_url(result):
    data = result.get("data") or []
    if not data:
        raise RuntimeError(f"Generation failed: {result}")

    image_url = data[0].get("url")
    if not image_url:
        raise RuntimeError(f"Image URL not found: {result}")

    return image_url


def download_image(image_url):
    response = requests.get(image_url, timeout=120)
    response.raise_for_status()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = OUTPUT_DIR / f"generated_{timestamp}.jpeg"
    filepath.write_bytes(response.content)

    return filepath


def main():
    response = requests.post(URL, headers=headers, data=payload, timeout=120)
    response.raise_for_status()

    result = response.json()
    image_url = get_image_url(result)
    filepath = download_image(image_url)

    print(f"Image saved to: {filepath}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc)
