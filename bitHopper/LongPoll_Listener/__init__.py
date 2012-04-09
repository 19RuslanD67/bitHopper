import gevent, logging, traceback, json, time
import btcnet_info
import bitHopper.Configuration.Workers
import bitHopper.Network
import bitHopper.Tracking
import bitHopper.LongPoll
import Conversion

known = {}
blocks = {}
def add_address(server, url):
    """
    Adds an address and starts the polling function
    """
    global known
    if server not in known:
        logging.info('Spawning Listener %s' % server)
        gevent.spawn(poll, server)
    if url[0] == '/' or url[0] == '\\':
        url = btcnet_info.get_pool(server)['mine.address'] + url
    known[server] = url
    
def handle(content, server):
    """
    Handles the content returned from a lp poll
    """
    try:
        content = json.loads(content)
    except:
        logging.debug(traceback.format_exc())
        return
    block = Conversion.extract_block(content)
    
    
    global blocks
    if block not in blocks:
        blocks[block] = {}
        bitHopper.LongPoll.trigger(content)
        
    if server not in blocks[block]:
        blocks[block][server] = int(time.time())
        logging.debug('%s, %s' % (server, block))
        
def poll(server):
    """
    Function for polling the LP servers and getting the results
    calls handle for everything it recieves
    """
    global known
    while True:
        try:
            #Figure out everthing we need
            url = known[server]
            request = {'params':[], 'id':1, 'method':'getwork'}
            headers = {}
            username, password = bitHopper.Configuration.Workers.get_single_worker(server)
            
            #If we have no user wait 5 minutes and try again
            if username == None:
                gevent.sleep(5*60)
                continue
                
            content, server_headers = bitHopper.Network.send_work( url, username, password, headers, request, timeout = 60*30)
                
            bitHopper.Tracking.add_work_unit(content, server, username, password)
            
            handle(content, server)
            
        except:
            logging.error(traceback.format_exc())

