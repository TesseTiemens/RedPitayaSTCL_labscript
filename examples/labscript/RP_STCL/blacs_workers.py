from blacs.tab_base_classes import Worker

from labscript import LabscriptError
import h5py
import zmq
import threading
import time
from time import sleep
import numpy as np
import zenoh
from heros import RemoteHERO
import heros

class lock_zmqThread(threading.Thread):
    """
    Special threading class that can be nicely stopped and handles all of the zmq backbone for us. 
    Avoids race conditions with a readwrite semaphore
    """
    def __init__(self,stream,values,rw_semaphore,):
        self.stream=stream
        self.address = stream['addr']
        self.port = stream['port']
        self.dt = stream['dt']
        self.topic = f"{stream['lock']} : {stream['slave']}"
        self.avg = stream['avg']
        self.values = values
        
        
        self.rw_semaphore = rw_semaphore
        

        #register the please stop as event that can be called at any time
        self._please_stop = threading.Event()

        threading.Thread.__init__(self,daemon=True)

    def run(self):
        #we set up a zmq subscriber
        with zmq.Context().socket(zmq.SUB) as socket: #do a with so it natually closes the socket at the end
            socket.setsockopt(zmq.SUBSCRIBE, self.topic.encode('UTF-8'))
            socket.setsockopt(zmq.RCVHWM,1)
            socket.RCVTIMEO = int(np.floor(self.dt*1000)) #dt is in seconds, rcvtimeo is in ms
            socket.connect(f"tcp://{self.address}:{self.port}")

            #loop untill we need to stop
            while not self._please_stop.is_set():
                try:
                    msg = socket.recv().decode('utf-8')
                    #print(msg)
                    val_list = msg.split(';') #we split after the topic, assuming it's [topic]: [value]
                    # print(val_list)
                    with self.rw_semaphore: #to avoid race conditions we get a semaphore here
                        try: #try converting the thing to float so we can do formatting
                            val_new = float(val_list[-1])

                            if self.avg is not None: #run the rolling average if this is set
                                #rint(val_new)
                                self.values[1:]  = self.values[:-1]
                                self.values[0] = val_new
                                #print(self.avgarr)
                            else:
                                self.values[0] = val_new
                        except:
                            pass
                except Exception as e: #mainly here to catch timeouts but I'm not sure what exception that throws
                    if isinstance(e,zmq.error.Again):
                        pass #ignore resource temp unavailable errors to avoid flooding the terminal 
                    else:
                        print('Something went wrong!')
                        print(e)
                
                #wait before trying to receive again. Since we ask the user to set dt to the exact send dt, we should here wait less than that to allow for the processing above
                #the timeout will take care of any other waiting.
                time.sleep(self.dt/2)
                
    def stop(self):
        self._please_stop.set()

class lock_zmq_stream():
    """
    Wrapper for the zmqThread, which allows us to cleanly read from the array, as well as clear it. Handles the semaphore and output cleanup for us.
    """
    def __init__(self,laserstream):
        self.laserstream = laserstream
        #set up the things we need to pass to the thread, set up the thread, and sets itup
        self.rw_semaphore = threading.Semaphore(1) #set up a semaphore to avoid race conditions
        if laserstream['avg']:
            self.outputs = np.zeros(laserstream['avg'])
        else:
            self.outputs = np.zeros(1)
        self.acq_thread = lock_zmqThread(self.laserstream,self.outputs,self.rw_semaphore)
        self.acq_thread.start()
    
    def clear_list(self):
        """
        Empties the output list of the zmq stream. When running with array=True, this should be called at transition_to_buffered
        """
        with self.rw_semaphore:
            if self.laserstream['avg']:
                self.outputs = np.zeros(self.laserstream['avg'])
            else:
                self.outputs = np.zeros(1) #this clears the list in-place, such that we can still access it from the thread
    
    def get_data(self):
        """
        Retrieves the received data from the zmq stream. Returns a 1d numpy array, dtype float 
        """
        with self.rw_semaphore:
            #since all the if array bullshit is taken care of in the thread, all we have to do is concatenate the whole thing
            out_val_str = np.stack(self.outputs) 
        out_val = out_val_str.flatten() #making sure the output is consitently shaped
               
        return out_val

    def close(self):
        self.acq_thread.stop()

class STCLWorker(Worker):
    def get_session_mgr(self):
            session = zenoh.open(zenoh.Config.from_file(self.zenoh_config))
            session_mgr = heros.zenoh.session_manager
            session_mgr._session=session
            return session_mgr
    
    def init(self):

        #We open the lock to check if things work, and to configure it for our needs
        with RemoteHERO(self.heros_name,session_manager=self.get_session_mgr()) as Lock:
            #figure out which RP does what
            modedict = Lock.get_RP_modes()

            #we loop through the RPs to find the correct ones
            self.monRP = None
            self.cavRP = None
            for key, val in modedict.items():
                if val == 'monitor':
                    self.monRP = key
                elif val == 'scan':
                    self.cavRP = key
            
            #if we didn't find one of them, error out
            if self.monRP is None or self.cavRP is None:
                    raise LabscriptError('Failed to find monitor and/or cavity RP. Make sure one RP is set to monitor and one RP is set to scan')

            #check what is running            
            lstatus = Lock.get_monitor_status(self.monRP)
            print(lstatus)
            
            # if sum(lstatus)== 0: #in case nothing is running, we might need to start the cavity scan 
            #     Lock.start()
            #     print("Starting scan on the cavity RP...")
            #     Lock.start_scan(self.cavRP) # Start cavity scan ramp
            #     sleep(1)        

            if self.emon_ip is not None:
                if bool(lstatus[1]):
                    print('Found existing error monitor instance, stopping...')
                    Lock.stop_monitor(self.monRP)
                    sleep(2)
                    if bool(lstatus[0]):
                            #in case normal monitoring was running, we should restart it
                            print('Restarting normal monitoring')
                            Lock.start_monitor(self.monRP)
                            #wait for it to start
                            mon_started=False
                            while not mon_started:
                                mon_started = bool(Lock.get_monitor_status(self.monRP)[0])
                                sleep(0.1)
                    
                print("Starting Error monitor")
                Lock.start_error_monitor(self.monRP,tmin=self.emon_tmin,zmq_pub=True,zmq_addr=None,zmq_port=self.emon_port) #Start error monitor with zmq enabled
                    
                #wait for the emon to start
                emon_started=False
                while not emon_started:
                    emon_started = bool(Lock.get_monitor_status(self.monRP)[1])
                    sleep(0.1)
                    
            
            lstatus_new = Lock.get_monitor_status(self.monRP)
            if not bool(lstatus_new[1]):
                print('Could not confirm startup of error monitor, please check')

        if self.emon_ip is not None:
            for stream in self.streams:
                stream['stream'] = lock_zmq_stream(stream)
                

        #setup smart cache
        self.smart_cache={}

        for laser in self.lasers:
            self.smart_cache[laser['name']] = None

    def transition_to_buffered(self,device_name,h5_filepath,initial_values,fresh=True):
        if fresh:
            for laser in self.lasers:
                self.smart_cache[laser['name']] = None
        
        self.h5_filepath = h5_filepath
        self.device_name = device_name
        setpoints_to_update = {}
        with h5py.File(self.h5_filepath, 'r+') as hdf_file:
            group = hdf_file[f'devices/{device_name}']
            for laser in self.lasers:
                lname = laser['name']
                #if there is a setpoint defined for this shot, the setpoint dataset exists
                if group[lname].__contains__('setpoint'):
                    new_setpoint = group[lname]['setpoint'][0] #grab the setpoint
                    print(new_setpoint)
                    if new_setpoint != self.smart_cache[lname]: #compare it to the smart_cache
                        setpoints_to_update[lname] = [laser['lock'],laser['slave'],new_setpoint] #we save this as a little list so we don't have to look this up in the laser dict later

        if setpoints_to_update: #to save time, we only open the remoteHERO if we actually need to change something
            with RemoteHERO(self.heros_name,session_manager=self.get_session_mgr()) as Lock:
                for key,val in setpoints_to_update.items():
                    print(f'setting {key} to {val[2]}')
                    Lock.update_setting(val[0],val[1],'lockpoint',val[2])
                    #we only wait for this to settle if it is not None
                    if self.error_margin is not None:
                        timestart = time.time()
                        settled = False
                        with zmq.Context().socket(zmq.SUB) as socket:
                            socket.setsockopt_string(zmq.SUBSCRIBE, f"{val[0]} : {val[1]}")
                            socket.setsockopt(zmq.RCVHWM,1)
                            socket.RCVTIMEO = int(2*self.emon_tmin*1000)# slightly longer than the publishing interval so the code does not hang endlessly
                            socket.connect(f"tcp://{self.emon_ip}:{self.emon_port}")
                            while not settled:
                                try:
                                    msg = socket.recv().decode('utf-8')
                                    mlist = msg.split(';')
                                    error = float(mlist[-1])
                                    print(f'Current error: {error:5.3f}, margin {self.error_margin} ')
                                    if np.abs(error)<self.error_margin and time.time()-timestart>0.1: #wait 100ms regardless in case we're a bit slow
                                        settled=True
                                except Exception as e:
                                    print(e)
                                if self.settle_timeout is not None and time.time()-timestart>self.settle_timeout:
                                    raise LabscriptError(f'Laser {key} did not settle in before Timeout of {self.settle_timeout} was reached')
                    self.smart_cache[key]=val[2]
        ## check if everything is still locked
        if self.emon_ip is not None:
            for stream in self.streams:
                vals = stream['stream'].get_data()
                print(stream['name'])
                erravg = np.average(vals)
                print(f'latest: {vals[0]}')
                print(f'running avg: {erravg}')
                print(f'RMS: {np.sqrt(np.average(np.square(vals)))}')
                if stream['name'] not in setpoints_to_update.keys(): #only check this if we didn't just change the value
                    if np.abs(erravg)>self.error_margin: #the average seems to give the best idea of the lock
                        print(f'WARNING: laser {stream['name']} appears unlocked')
                        if self.error_on_unlock:
                            raise LabscriptError(f'Laser {stream['name']} exceeded the error treshold of {self.error_margin}, reaching a value of {erravg}. Is it still locked?')
                    else:
                        print(f'Laser {stream['name']} PASS')
        return initial_values
        
    def transition_to_manual(self):
        return True
    
    def program_manual(self,frontpanel_values):
        pass
    
    def abort(self):
        return True
    def abort_transition_to_buffered(self):
        return self.abort()
    def abort_buffered(self):
        return self.abort()
    
    def shutdown(self):
        pass