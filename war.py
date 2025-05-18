"""
war card game client and server
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import socket
import socketserver
import threading
import sys


"""
Namedtuples work like classes, but are much more lightweight so they end
up being faster. It would be a good idea to keep objects in each of these
for each game which contain the game's state, for instance things like the
socket, the cards given, the cards still available, etc.
"""
Game = namedtuple("Game", ["p1", "p2"])

# Stores the clients waiting to get connected to other clients
waiting_clients = []


class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3


class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2

def readexactly(sock, numbytes):
    """
    Accumulate exactly `numbytes` from `sock` and return those. If EOF is found
    before numbytes have been received, be sure to account for that here or in
    the caller.
    """
    data = b""
    while len(data) < numbytes:
        chunk = sock.recv(numbytes - len(data))
        if not chunk:
            raise EOFError("socket closed before receiving sufficient data")
        data += chunk
    return data


def kill_game(game):
    """
    TODO: If either client sends a bad message, immediately nuke the game.
    """
    logging.debug("Killing game")
    for s in (game.p1, game.p2):
        try:
            s.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            s.close()
        except Exception:
            pass


def compare_cards(card1, card2):
    """
    TODO: Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    r1, r2 = card1 % 13, card2 % 13
    logging.debug("Comparing cards: %d, %d", card1, card2)
    return -1 if r1 < r2 else (1 if r1 > r2 else 0)
    

def deal_cards():
    """
    TODO: Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """
    logging.debug("Shuffling and dealing cards")
    deck = list(range(52))
    random.shuffle(deck)
    return deck[:26], deck[26:]
    

def serve_game(host, port):
    """
    TODO: Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """

    def play_game(game):
        p1, p2 = game.p1, game.p2
        try:
            for s in (p1, p2):
                logging.debug("WANT GAME 00")
                cmd, payload = readexactly(s, 2)
                if cmd != Command.WANTGAME.value or payload != 0:
                    raise ValueError("bad WANTGAME")

            hand1, hand2 = deal_cards()
            logging.debug("Dealt cards [Player 1: %d, Player 2: %d]", len(hand1), len(hand2))
            p1.sendall(bytes([Command.GAMESTART.value]) + bytes(hand1))
            p2.sendall(bytes([Command.GAMESTART.value]) + bytes(hand2))
            
            logging.debug("GAME START 01")
            remaining1, remaining2 = set(hand1), set(hand2)

            for i in range(26):
                logging.debug("round %d", i)
                
                c1_cmd, c1 = readexactly(p1, 2)
                c2_cmd, c2 = readexactly(p2, 2)
                logging.debug("PLAY CARD 02 [P1: %d, P2: %d]", c1, c2)
                
                if c1_cmd != Command.PLAYCARD.value or c2_cmd != Command.PLAYCARD.value:
                    raise ValueError("bad PLAYCARD command")
                if c1 not in remaining1 or c2 not in remaining2:
                    raise ValueError("duplicate/illegal card")

                remaining1.remove(c1)
                remaining2.remove(c2)

                cmp = compare_cards(c1, c2)
                if cmp == 1:
                    res1, res2 = Result.WIN, Result.LOSE
                    logging.debug("PLAY RESULT 03 : p1 wins")
                elif cmp == -1:
                    res1, res2 = Result.LOSE, Result.WIN
                    logging.debug("PLAY RESULT 03 : p2 wins")
                else:
                    res1 = res2 = Result.DRAW

                p1.sendall(bytes([Command.PLAYRESULT.value, res1.value]))
                p2.sendall(bytes([Command.PLAYRESULT.value, res2.value]))

        except Exception as exc:
            kill_game(game)
            return
        finally:
            for s in (p1, p2):
                try:
                    s.close()
                except Exception:
                    pass

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, port))
    server_sock.listen()
    logging.info("WAR server listening on %s:%d", host, port)
    logging.debug("Server socket created (host: %s, port: %d)", host, port)

    try:
        while True:
            client_sock, addr = server_sock.accept()
            logging.debug("Client connected from %s:%d", *addr)
            waiting_clients.append(client_sock)

            if len(waiting_clients) >= 2:
                s1 = waiting_clients.pop(0)
                s2 = waiting_clients.pop(0)
                logging.debug("Starting game 00")
                threading.Thread(target=play_game,
                                 args=(Game(s1, s2),),
                                 daemon=True).start()
    finally:
        server_sock.close()
    

async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)

async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port)
        logging.debug("WANT GAME 00")
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        logging.debug("GAME START 01")

        myscore = 0
        for card in card_msg[1:]:
            logging.debug("PLAY CARD 02 [card=%d]", card)
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
                logging.debug("PLAY RESULT 03 [win, score = %d]", myscore)
            elif result[1] == Result.LOSE.value:
                logging.debug("PLAY RESULT 03 [lose, score = %d]", myscore)
                myscore -= 1
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.debug("Game Over! You %s!", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0

def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        
        asyncio.set_event_loop(loop)
        
    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]
        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients
        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()

if __name__ == "__main__":
    # Changing logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1:])