"""
This module contains all of the server selection logic.
It supplies one function:
get_server() which returns the name of a server to mine.

It has two external dependencies.
1) btcnet_info via btcnet_wrapper
2) a way to pull getworks for checking if we should delag pools


"""


import ServerLogic
import bitHopper.Configuration.Workers as Workers
    
def get_server():
    """
    Returns a valid server, worker, username tuple
    Note this isn't quite a perfectly even distribution but it 
    works well enough
    """
    return _select(list(generate_tuples(ServerLogic.get_server())))
    
i = 0

def generate_tuples( server):
    """
    Generates a tuple of server, user, password for valid servers
    """
    tokens = Workers.get_worker_from(server)
    for user, password in tokens:
        yield (server, user, password)
    
def _select(item):
    """
    Selection utility function
    """
    global i
    i = i + 1 if i < 10**10 else 0
    if len(item) == 0:
        raise ValueError("No item available")
    return item[i % len(item)]
