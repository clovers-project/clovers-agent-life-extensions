if __name__ == "__main__":
    import base64
    import hashlib
    import puremagic

    from pathlib import Path

    def to_b64url(data: bytes) -> str | None:
        mime = puremagic.from_string(data, mime=True).split("/", 2)
        if len(mime) != 2:
            return
        mime, subtype = mime
        b64 = base64.b64encode(data).decode()
        return f"data:{mime}/{subtype};base64,{b64}"

    LOCAL_PATH = Path(__file__).parent
    IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".gif")

    images = [x for x in LOCAL_PATH.iterdir() if x.suffix.lower() in IMAGE_TYPES]
    for image in images:
        b64url = to_b64url(image.read_bytes())
        if not b64url:
            continue
        file = LOCAL_PATH / f"{hashlib.md5(b64url.encode()).hexdigest().upper()}.b64"
        file.write_text(b64url)
        image.unlink()
