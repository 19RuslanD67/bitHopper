from getwork_store import Getwork_Store
from bitHopper.util import extract_merkle

__store = False

def __patch():
    global __store
    if note __store:
        __store = Getwork_Store()
        
    

def add_work_unit(content, server, username, password):
    """
    Does wrapping and stores the result
    """
    __patch()
    merkle_root = extract_merkle(content)
    if not merkle_root:
        return
    auth = (server, username, password)
    __store.add(merkle_root, auth)
    
def get_work_unit(content):
    """
    Does wrapping and returns the result
    """
    merkle_root = extract_merkle(content)
    if not merkle_root:
        return (None, None, None)
    auth = __store.get(merkle_root)
    if not auth:
        return (None, None, None)
    return auth
