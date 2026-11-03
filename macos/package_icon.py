"""Package generated PNG representations into the documented ICNS chunk format."""
import struct
import sys
from pathlib import Path

source, destination = map(Path, sys.argv[1:])
representations = {
    b"icp4": "icon_16x16.png", b"icp5": "icon_32x32.png",
    b"icp6": "icon_32x32@2x.png", b"ic07": "icon_128x128.png",
    b"ic08": "icon_256x256.png", b"ic09": "icon_512x512.png",
    b"ic10": "icon_512x512@2x.png", b"ic11": "icon_16x16@2x.png",
    b"ic12": "icon_32x32@2x.png", b"ic13": "icon_128x128@2x.png",
    b"ic14": "icon_256x256@2x.png",
}
chunks = []
for kind, filename in representations.items():
    data = (source / filename).read_bytes()
    chunks.append(struct.pack(">4sI", kind, len(data) + 8) + data)
body = b"".join(chunks)
destination.write_bytes(struct.pack(">4sI", b"icns", len(body) + 8) + body)
