from lockclient import LockClient, RP_client
from heros import LocalHERO
import time
import numpy
import zenoh
import heros

class LockClient_heros(LocalHERO,LockClient):
    '''
    Little wrapper class that combines the LockClient with a HEROS class. This way we don't have to mess with the rest of the code.
    Seems to work fine this way. Note that attributes don't get passed
    '''
    def __init__(self, name, redpitayas, FSR=906, DIR=None):
        LocalHERO.__init__(self,name)
        LockClient.__init__(self,redpitayas=redpitayas,FSR=FSR,DIR=DIR)
        print('Rebuilding heros capabilities')
        self._capabilities() #just to make sure it's up-to-date

if __name__ == "__main__":
    # The dictionary RPs contains all the information of the lock
    RPs = dict(
        Cav = RP_client(("192.168.0.55", 5000), {}, mode = 'scan'),
        Lock1 = RP_client(("192.168.0.101", 5000), {}, mode = 'lock'),
        #Lock2 = RP_client(('192.168.0.106', 5000), {}, mode= 'lock'),
        Mon = RP_client( ('192.168.0.103', 5000), {}, mode = 'monitor') 
        )
    
    #name of the HEROS object, change if need be
    name = 'SCTL'
    #obtain the session
    with zenoh.open(zenoh.Config.from_file('./examples/labscript/zenoh_config_peer.json5')) as session:
            session_mgr = heros.zenoh.session_manager
            session_mgr._session = session
            with LockClient_heros(name,RPs) as Lock:
                #set up the lock locally
                Lock.start()

                # Make sure that the lock is not running
                # These are debugging things that we can only do here, since Lock.RPs is not exposed over HEROs
                Lock.RPs['Cav'].lsock = None # listening server, if it is not properly closed
                Lock.RPs['Cav'].loop_running = False

                print("Starting scan on the cavity RP...")
                Lock.start_scan('Cav')

                #wait for the cavity scan to actually start
                time.sleep(2)

                # This line starts the monitoring script which creates the window where you can see the
                # cavity signal across roughly 2 FSRs of the HeNe laser
                print("Starting monitor...")
                Lock.start_monitor('Mon')
                
                #now we just sleep
                print(f'Started remote hero at name {name}')
                while True:
                    time.sleep(1)