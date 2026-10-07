import os
import socket
from typing import Final

port: Final[int] = int(os.environ.get("PORT", "4000"))
listener: Final[socket.socket] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(("0.0.0.0", port))
listener.listen(2048)
listener.set_inheritable(True)
os.environ["LITELLM_SERVER_FD"] = str(listener.fileno())
os.execv("/bin/sh", ["/bin/sh", "/app/deploy/start.sh"])
