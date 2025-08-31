
import websockets 
from websockets import Subprotocol
from util.client_cosmic import Cosmic, console
from config import ClientConfig as Config


class Handler:
    def __enter__(self):...

    def __exit__(self, exc_type, e, exc_tb):
        if e == None:
            return True
        if isinstance(e, ConnectionRefusedError):
            return True
        elif isinstance(e, TimeoutError):
            return True
        elif isinstance(e, Exception):
            return True
        else:
            print(e)


async def check_websocket() -> bool:
    if Cosmic.websocket and Cosmic.websocket.state.name == 'OPEN':
        return True
    for _ in range(3):
        with Handler():
            # Configure WebSocket with extended keepalive settings
            Cosmic.websocket = await websockets.connect(
                f"ws://{Config.addr}:{Config.port}", 
                max_size=None, 
                subprotocols=[Subprotocol("binary")],
                ping_interval=20,        # Send ping every 20 seconds
                ping_timeout=60,         # Wait 60 seconds for pong response
                close_timeout=1,         # Timeout for graceful close
                max_queue=1024           # Maximum message queue size
            )
            return True
    else:
        return False

    # for _ in range(3):
    #     try:
    #         Cosmic.websocket = await websockets.connect(f"ws://{Config.addr}:{Config.port}", max_size=None)
    #         return True
    #     except ConnectionRefusedError as e:
    #         continue
    #     except TimeoutError:
    #         continue
    #     except Exception as e:
    #         print(e)
    #
    # else:
    #     return False
