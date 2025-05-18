import threading
import asyncio
import time
import logging

from war import serve_game, client, limit_client

HOST = '127.0.0.1'
PORT = 12345

def start_server():
    serve_game(HOST, PORT)

async def run_clients(num_clients):
    sem = asyncio.Semaphore(1000)
    clients = [limit_client(HOST, PORT, asyncio.get_running_loop(), sem) for _ in range(num_clients)]

    completed = 0
    for coro in asyncio.as_completed(clients):
        completed += await coro
    return completed

def main():
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    time.sleep(1)

    num_clients = 10
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    completed_clients = loop.run_until_complete(run_clients(num_clients))
    logging.info("%d clients completed", completed_clients)

    assert completed_clients == num_clients, "Not all clients completed!"

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
