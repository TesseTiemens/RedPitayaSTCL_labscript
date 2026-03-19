# -*- coding: utf-8 -*-
"""
Created on Fr Feb 27 14:01:26 2026

@author: CaF Experiment
"""



#%% Locking initialization
from time import sleep
from heros import RemoteHERO
import zenoh
import heros


lock_dict={
    "Reference":{"Lock": "Cav",
               "Slave": "Master",
               },
    "Vexlum": {"Lock": "Lock1",
               "Slave": "Slave1",
               },
    
    "RepumpA1": {"Lock": "Lock1",
               "Slave": "Slave2",
               },
    "Slower": {"Lock": "Lock2",
               "Slave": "Slave1",
               }
       }

#function we can use to run other code
def get_lock():
    session = zenoh.open(zenoh.Config.from_file('zenoh_config_peer.json5')) #edit this to point to your local config
    session_mgr = heros.zenoh.session_manager
    session_mgr._session = session
    return RemoteHERO('SCTL',session_manager=session_mgr)


#%% functions

def gamma_to_lockpoint(laser,detuning_gamma):
    
    if laser == "Vexlum":
        scaling_factor = -0.087/8 # 0.087 corresponds to 8 Gamma on the cavity
        det_zero=0.951
        
    elif laser == "Slower":
        scaling_factor =-1 
        det_zero=0
        
    else:
        print(f"Error:Laser not found")
        det_zero=-1
        scaling_factor=0
    print(f"{det_zero}####{scaling_factor}####{detuning_gamma}")    
    lockpoint = det_zero + scaling_factor * detuning_gamma 
    
    return lockpoint
def update_range(laser,ranges):
    with get_lock() as Lock:
        Lock.update_setting(lock_dict[laser]["Lock"], lock_dict[laser]["Slave"], 'range',ranges) 

def update_lockpoint(laser,lockpoint):
    with get_lock() as Lock:
        Lock.update_setting(lock_dict[laser]["Lock"], lock_dict[laser]["Slave"], 'lockpoint', lockpoint) 
    
def update_PID(laser,PID):
    with get_lock() as Lock:
        Lock.update_setting(lock_dict[laser]["Lock"], lock_dict[laser]["Slave"], 'PID', PID) 
    
def update_enabled(laser,enabled):
    with get_lock() as Lock:
        Lock.update_setting(lock_dict[laser]["Lock"], lock_dict[laser]["Slave"], 'enabled', enabled) 
    
def update_sign(laser,sig):
    with get_lock() as Lock:
        Lock.update_setting(lock_dict[laser]["Lock"], lock_dict[laser]["Slave"], 'sign', sig) 
    
def update_inverse(laser,inv):
    with get_lock() as Lock:
        Lock.update_setting(lock_dict[laser]["Lock"], lock_dict[laser]["Slave"], 'invert', inv) 

def toggle_cavity_lock(cavity_locked, lock1_inactive):
    """Toggles the cavity lock with a safety confirmation if lasers are active."""
    # Safety check: if lasers are currently active, warn the user before unlocking
    
    if not lock1_inactive:
        input("Laser Lock is active.\n"
              "Press Return if you are sure that you want to unlock the cavity.\n"
              "Press Ctrl+C to cancel.")
        
    with get_lock() as Lock:
        Lock.stop_loop('Cav')
        sleep(0.5)
        
        if not cavity_locked:
            Lock.start_lock('Cav')
            print("Cavity: Start lock!")
        else:
            Lock.start_scan('Cav')
            print("Cavity: Stop lock!")
    
    return not cavity_locked

def toggle_laser_lock(lock_name, is_inactive):
    """Generic function to toggle Lock1, Lock2, etc."""
    with get_lock() as Lock:
        if is_inactive:
            Lock.start_lock(lock_name)
            print(f"Starting {lock_name}!")
        else:
            Lock.stop_loop(lock_name)
            print(f"Stopping {lock_name}!")
        
        new_state = not is_inactive
        status = "Deactivating" if new_state else "Activating"
        print(f"{status} {lock_name}!")
    
    return new_state



#%% main
if __name__ == "__main__":
    # Making sure the script is only run intentionally
    input("Are you sure you want to restart the entire script?")
    
    
    ###### all of this is handled by the heros lock script ######
    # The dictionary RPs contains all the information of the lock
    # RPs = dict(
    #     Cav = RP_client(("192.168.0.55", 5000), {}, mode = 'scan'),
    #     #Cav = RP_client(("192.168.0.101", 5000), {}, mode = 'scan'), ## remove, testing the lock on 20250124
    #     Lock1 = RP_client(("192.168.0.101", 5000), {}, mode = 'lock'),
    #     Lock2 = RP_client(('192.168.0.106', 5000), {}, mode= 'lock'),
    #     Mon = RP_client( ('192.168.0.103', 5000), {}, mode = 'monitor') 
    #     )
    
    # # Initialize the lock with the dictionary created above
    # Lock = LockClient(RPs)
    # sleep(5)
    # # Make sure that the lock booleans are set to "unlocked"
    cavity_locked = False
    lock1_inactive = True
    lock2_inactive = True
    

#%% Setup Locking Parameters
    
    #Reference Laser
    update_range('Reference', [[0.25, 0.5], [1.6, 1.8]])
    update_lockpoint('Reference', 1.71)
    update_PID('Reference', {"P": 0.1, "I": 7, "D": 0.0})
    
    #Repumper A 1
    update_enabled('RepumpA1', False)
    update_sign('RepumpA1', -1)
    update_PID('RepumpA1', {"P": 0, "I": 50, "D": 0.0})
    update_range('RepumpA1', [1.11, 1.48])
    update_lockpoint('RepumpA1', 1.42)
  
    
    #Vexlum
    update_enabled('Vexlum', True)
    update_sign('Vexlum', 1)
    update_PID('Vexlum', {"P": 0, "I": 50}) # PID Scan: (0,50,0)
    update_range('Vexlum', [0.5, 1.6])
    update_lockpoint('Vexlum', 1.137)
    
    # Slower
    update_enabled('Slower', False)
    update_sign('Slower', 1) # locking: +1 for piezo, -1 for current
    update_PID('Slower', {"P": 0.1, "I": 5, "D": 0}) # PID Scan 20251107
    update_range('Slower', [0.51, 0.90])
    update_lockpoint('Slower', 0.665)
    

#%% Good FSR (New FSR: 20250602) - Don't touch or else...

    # --- Vexlum ---
    # Spectroscopy 20251002 (Downstairs Wavemeter F=0: 494.431966 THz)
    update_enabled('Vexlum', True)
    update_range('Vexlum', [0.73, 1.3])
    update_lockpoint('Vexlum', 0.951)
    
    # --- Repump A 1 (R1) ---
    # Spectroscopy 20250508
    update_enabled('RepumpA1', True)
    update_range('RepumpA1', [1.31, 1.58])
    update_lockpoint('RepumpA1', 1.46)
    
    # --- Slower ---
    # Spectroscopy 20250530 (Wavemeter: 564.582529 THz)
    update_enabled('Slower', True)
    update_range('Slower', [0.5, 0.72])
    update_lockpoint('Slower', 0.655)
    
#%%  # Toggling the Cavity
    cavity_locked = toggle_cavity_lock(cavity_locked, lock1_inactive)
#%% # Toggling Lock1
    lock1_inactive = toggle_laser_lock('Lock1', lock1_inactive)

#%%    # Toggling Lock2
    lock2_inactive = toggle_laser_lock('Lock2', lock2_inactive)
    
    #%% To change the lockpoint of the vexlum for manual scans
    
    detuning_in_gamma = 2
    scaling_factor = -0.087/8 # 0.087 corresponds to 8 Gamma on the cavity
    setpoint_change_for_detuning = scaling_factor * detuning_in_gamma #5
    update_lockpoint('Vexlum', 0.951 + setpoint_change_for_detuning)# setpoint = 0.951 
    print(f'Detuning = {detuning_in_gamma} Gamma')
    
   
    
#%% Start error Monitor
    with get_lock() as Lock:    
        Lock.start_error_monitor('Mon', tmin = 30e-3, zmq_pub=True)
    

#%% Saving error data
    from datetime import datetime
    
    with get_lock() as Lock:
        try:
            Lock.mon_queue_put('Mon','queue_err','save', 'data' + '\\error_array_' + str(int(datetime.now().timestamp())))
            print("Saved error array.")
        except:
            print("Couldn't save error array, probably the cavity lock was not used.")
