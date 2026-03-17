from labscript import LabscriptError, Device,set_passed_properties
import numpy as np
class Laser():
    '''A lil class to hold the laser parameters and allow us to neatly set the lockpoint'''
    def __init__(self,laser_name,lock,slave):
        self.name = laser_name
        self.lock = lock
        self.slave = slave
        self.setpoint = None #we init to None so we can distinguish if something has been set or not
    
    def update_lockpoint(self,lockpoint):
        self.setpoint = lockpoint
    
    def get_attrdict(self):
        return {'name':self.name,'lock':self.lock,'slave':self.slave}

class RP_STCL(Device):
    """A pseudo-device for interacting with the STCL

    Args:
        name (str): The name of the device.
        heros_name (str): The name of the remote heros object
        parent_device (Device,optional): The parent device to which this device is connected.
        conneciton (string, optional): the connection on the parent device
        zenoh_config (string, optional): The location of the zenoh config json
        emon_ip (string or None, optional): The IP address of the pc that will run the error monitor. If set to anything but none, 
            the code will (re)start the error monitor with zmq publishing enabled for all interfaces at port emon_port
        emon_port (int, optional): The port for the error monitor zmq stream. Defaults to 6200
        emon_tmin (float, optional): minimum time between error monitor points
        error_margin (float or None, optional): if not None, gives the error margin (in GHz) to wait for while laser is setteling. If none, disables wait. Defaults to None
        settle_timeout (float or None, optional): if not None, gives the timeout for waiting for the laser to settle. 
        avg (int or None, optional): if not None, sets number of averages for the rolling average, used for displaying the error, and also for checking at each shot if the laser is still locked
            If None, averaging is disabled. Defaults to 10
        error_on_unlock (bool, optional): If set, the code will check at the beginning of each shot if the rolling average of the error has exceeded, error_margin, and if it has, will error out
            Defaults to True
    """
    description = "A pseudo-device for logging zmq data streams"
    allowed_children=[]

    @set_passed_properties(property_names={'connection_table_properties':['heros_name','zenoh_config','emon_ip','emon_port','emon_tmin','error_margin', 'settle_timeout','avg','error_on_unlock']})
    def __init__(self, name, heros_name, parent_device=None,connection=None,zenoh_config=None, 
                 emon_ip=None, emon_port=6200, emon_tmin = 30e-3,
                 error_margin = None, settle_timeout = None, 
                 avg=10,error_on_unlock=True):
        self.name=name
        #Preventing stupidity
        if error_margin is not None and emon_ip is None:
            raise LabscriptError('Cannot have error margin set without an IP for the error monitor')
        #here we just warn since the default behaviour is True
        if emon_ip is None and error_on_unlock:
            print('WARNING: no emon_ip set, setting error_on_unlock to False')
            error_on_unlock = False
            self.set_property('error_on_unlock',error_on_unlock,location='connection_table_properties',overwrite=True)
        
        self.lasers = []
        self.BLACS_connection = name
        Device.__init__(self,name,parent_device,connection=self.BLACS_connection)

    #set a log stream to be opened in the labscript device
    def add_laser(self,laser_name:str,lock:str,slave:str):
        """
        Add a laser to the lock, with settings that match your STCL settings files. The lasers get added to the attributes of the STCL class, 
        so you can update their locpoints by doing for instance RP_STCL.vexlum.update_lockpoint()

        Args:
            laser_name (str):   Name of the laser
            lock (str):         Which locking RP the laser is connected to
            slave (str):        The 'slave point' of the laser
        """
        # self.AIs.append(AnalogIn(stream_name,self,f'{address}:{port}'))
        self.__setattr__(laser_name,Laser(laser_name=laser_name,lock=lock,slave=slave))
        self.lasers.append(self.__getattribute__(laser_name).get_attrdict())
        self.set_property('lasers',self.lasers,location='connection_table_properties',overwrite=True)

    def generate_code(self, hdf5_file):
        print(self.name)            
        Device.generate_code(self,hdf5_file)
        grp = self.init_device_group(hdf5_file)

        #loop through all the lasers we have added
        for laser in self.lasers:
            print(laser)
            #get the lasers name
            lname = laser['name']

            #create a group in the h5 file for it
            lgroup = hdf5_file.require_group(f'devices/{self.name}/{lname}')

            #get its setpoint
            laser_obj = self.__getattribute__(lname)
            setpoint = laser_obj.setpoint
            print(f'setpoint: {setpoint}')

            #in case it was set, it is not None, and so we create a dataset that contains it
            if setpoint:
                lgroup.create_dataset('setpoint',data=np.array([setpoint]))